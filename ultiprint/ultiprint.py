#!/usr/bin/env python

#
# Copyright (C) 2014 Erwin Rieger
#
#

#
# XXX todo: mov gcode packing into a preprocessing task, prevent errors at printing time
#

#
#
# Acknowledge of a usb transmission:
#   One byte, Ascii-ACK (0x6)
#
#
# Compression:
#
# N5860 G1 F3000 X153.16 Y123.17 Z38.80 E459.21186*62 -> 51 bytes
# 
# 1 byte:            command 1-9
# 1 byte:            'parameter mask', bits: FXYZES00 (2 unused bytes)
# 2 byte:            F param
# 4 byte:            X param
# 4 byte:            Y param
# 4 byte:            Z param
# 4 byte:            E param
# 4 byte:            2 or 4byte line counter, am schluss, damit einfach abzuschneiden
# 1 byte:            checksum
# 
# 


import sys, string, time, select, struct

from serial import Serial, SerialException, PARITY_NONE


# Create gcode checksum, this is stolen from
# printrun/printcore.py ;-)
def checksum(command):
    return reduce(lambda x, y: x ^ y, map(ord, command))


def packGCode(code, lineNr):

    # Note: Arduino is little endian

    if not code:
        return None

    splitted = code.split()

    cmd = splitted[0]

    if cmd == "G0" or cmd == "G1":

        assert(len(splitted) <= 6)

        cmdHex = 1
        if cmd == "G1":
            cmdHex = 2

        paramFlags = 0
        fHex = None
        xHex = None
        yHex = None
        zHex = None
        eHex = None

        for param in splitted[1:]:

            paramType = param[0]

            if paramType == "F":
                paramFlags += 1 << 7
                sp = int(param[1:])
                assert((sp > 0) and (sp < pow(2,16)))
                fHex = struct.pack("<H", sp)
                
            elif paramType == "X":
                paramFlags += 1 << 6
                fp = float(param[1:])
                xHex = struct.pack("<f", fp)

            elif paramType == "Y":
                paramFlags += 1 << 5
                fp = float(param[1:])
                yHex = struct.pack("<f", fp)

            elif paramType == "Z":
                paramFlags += 1 << 4
                fp = float(param[1:])
                zHex = struct.pack("<f", fp)

            elif paramType == "E":
                paramFlags += 1 << 3
                fp = float(param[1:])
                eHex = struct.pack("<f", fp)

            else:
                assert(0)

        lnHex = struct.pack("<I", lineNr)
        if lineNr < 0x10000:
            # pack line number as short
            paramFlags += 1 << 2
            lnHex = struct.pack("<H", lineNr)

        packed = struct.pack("<BB", cmdHex, paramFlags)

        if fHex:
            packed += fHex
        if xHex:
            packed += xHex
        if yHex:
            packed += yHex
        if zHex:
            packed += zHex
        if eHex:
            packed += eHex

        # add number and checksum
        packed += lnHex

        chk = checksum(packed)
        packed += struct.pack("<B", chk)

        return packed + "\n"


class Printer(Serial):

    def __init__(self, mode):
        Serial.__init__(self, port = sys.argv[1],
            # baudrate = 250000,
            # baudrate = 38400,
            baudrate = 115200,
            timeout = 0, parity = PARITY_NONE)

        self.lineno = 0
        if mode == "print":
            # self.endTokens = ["Done printing", 'echo:enqueing "M84"']   
            self.endTokens = ['echo:enqueing "M84"']   
        else:
            self.endTokens = ["Done saving", 'echo:enqueing "M84"']

        self.mode = mode
        self.cmdIndex = 0
        self.lastSend = 0

    # Check a printer response for an error
    def checkError(self, recvLine):

        if "Error:" in recvLine and  "Last Line" in recvLine:
            # Error:Line Number is not Last Line Number+1, Last Line: 9            
            # Error:checksum mismatch, Last Line: 71388
            lastLine = int(recvLine.split(":")[2])

            print "\nERROR:"
            print "Reply: ", recvLine,
            print "Scheduling resend of command...", lastLine+1

            # assert(self.cmdIndex == lastLine + 2)
            # assert(self.lineno == lastLine + 2)

            self.cmdIndex = lastLine + 1
            self.lineno = lastLine+1

            # Slow down a bit in case of error
            time.sleep(0.1)
            return True

        for token in ["Error:", "cold extrusion", "SD init fail", "open failed"]:
            if token in recvLine:

                print "\nERROR:"
                print "Reply: ", recvLine,
                sys.stdout.flush()
                self.readMore(20)

                self.reset()

                print "\n\nPrinter reset done, bailing out...\n\n"
                assert(0)

    # Read a response from printer, "handle" exceptions
    def saveReadline(self):

        result = ""

        while True:
            try:
                c = self.read()
                # print "c: ", c
            except SerialException as ex:
                print "Readline() Exception raised:", ex
                break

            if not c:
                break

            result += c

            if c == "\n":
                break

            if ord(c) == 0x6:
                result += "\n"
                break

        return result

    # Monitor printer responses for a while (wait waitcount * 0.1 seconds)
    def readMore(self, waitcount=100):

        print "waiting %.2f seconds for more messages..." % (waitcount/10.0)
        sys.stdout.flush()

        for i in range(waitcount):

            readable, writable, exceptional = select.select([self], [], [], 0.1)

            if exceptional:
                print "exception on select: ", exceptional
                self.reset()
                print "\n\nPrinter reset done, bailing out...\n\n"
                assert(0)

            if readable:
                recvLine = self.saveReadline()        

                assert(recvLine)

                if recvLine:
                    print "Reply: ", recvLine,
                    sys.stdout.flush()

    # Stop and reset the printer
    def reset(self):

        print "\nResetting printer"
        self._send("M29\n") # End sd write, response: "Done saving"
        self.readMore(25)

        self._send("M0\n") # Stop print
        self.readMore(25)

        self._send("G28\n") # Home all Axis, response: ok
        self.readMore(25)

        self._send("M84\n") # Disable steppers until next move, response: ok
        self.readMore(25)

        self._send("M104 S0\n") # Set temp
        self.readMore(25)

        self._send("M140 S0\n") # Set temp
        self.readMore(25)

    # Add linenumber and checksum to command 'cmd' and send it
    # to the printer.
    def send(self, cmd):

        if cmd == "M110":
            # reset line number
            self.lineno = 0

        packed = packGCode(cmd.strip(), self.lineno)
        if packed:
        
            print "\nSend: ", packed.encode("hex"), "%.1f%%" % ((len(packed)-5)*100.0/len(cmd))
            sys.stdout.flush()
            self.write(packed)
            self.lineno += 1
            return

        prefix = "N" + str(self.lineno) + " " + cmd.strip()
        cmd = prefix + "*" + str(checksum(prefix))

        self._send(cmd)
        self.lineno += 1

    # Send a command to the printer, add a newline if 
    # needed.
    def _send(self, cmd):

        if cmd[-1] != "\n":
            cmd += "\n"

        print "\nSend: ", cmd,
        sys.stdout.flush()
        self.write(cmd)


    # The 'mainloop' process each command in the list 'gcode', check
    # for the required responses and do errorhandling.
    def sendGcode(self, gcode, wantReply=None, waitForEndReply=True):

        self.cmdIndex = 0

        recvPart = None

        wantAck = False

        while True:

            if not wantAck and not wantReply and self.mode != "monitor" and self.cmdIndex < len(gcode):
                # send a line
                (line, wantReply) = gcode[self.cmdIndex]
                self.send(line)
                self.cmdIndex += 1
                self.lastSend = time.time()
                wantAck = True

            readable, writable, exceptional = select.select([self], [], [])

            if exceptional:
                print "exception on select: ", exceptional
                self.reset()
                print "\n\nPrinter reset done, bailing out...\n\n"
                assert(0)

            recvLine = self.saveReadline()        

            if not recvLine:
                continue

            # print "R0:", ord(recvLine[0])

            if recvPart:
                recvLine = recvPart + recvLine
                recvPart = None

            if recvLine[-1] != "\n":
                recvPart = recvLine
                continue

            if self.mode != "monitor" and self.checkError(recvLine):
                # command resend
                wantAck = False
                wantReply = None
                continue

            if wantAck and recvLine[0] == chr(0x6):
                print "ACK"
                wantAck = False
                continue

            if wantReply and recvLine.startswith(wantReply):
                print "Got Required reply: ", recvLine,
                wantReply = None
            else:
                print "Reply: ", recvLine,

            sys.stdout.flush()

            if waitForEndReply:
                for token in self.endTokens:
                    if recvLine.startswith(token):

                        sys.stdout.flush()
                        self.readMore()

                        print "end-reply received, exiting..."
                        sys.stdout.flush()
                        return

            elif not wantReply and self.cmdIndex == len(gcode):

                print "\nsent %d commands,  exiting..." % len(gcode)
                sys.stdout.flush()

                self.readMore()
                return





# 
#
# Main
#

if __name__ == "__main__":

    mode = sys.argv[2]
    if mode in ["store", "print"]:
        filename = sys.argv[3]

    assert(mode in ["print", "store", "reset", "monitor"])

    printer = Printer(mode)

    # Read left Garbage
    # printer.readMore(20)
    recvLine = printer.saveReadline()        
    print "Inital read: "
    print recvLine, "\n"

    if mode == "reset":
        printer.reset()
        sys.exit(0)

    # Always reset line counter first
    gcode = [("M110", "ok")]

    # If in printing mode, then send custom M623 command,
    # select file for UM2 print
    if mode == "print":
        gcode += [("M623 usb.g", "ok")]

    if mode != "monitor":

        # Store or print mode, open the file on the
        # SD card with the M28 command, then send the
        # contents of the file given on the commandline.
        # Close file on SD card with M29 if done.
        gcode += [("M28 usb.g", "ok")]

        inFile = open(filename)

        print "Storing and auto-printing", filename
        sys.stdout.flush()

        for line in inFile.readlines():

            # Strip very long line ";CURA_PROFILE_STRING" at the end:
            # Marlin: #define MAX_CMD_SIZE 96
            # if len(line) > 80:
                # line  = line[:80]
            if "CURA_PROFILE_STRING" in line:
                continue

            gcode.append((line, None))

        gcode += [("M29", "Done saving")]

        inFile.close()

    printer.sendGcode(gcode, "echo:SD card ok")



