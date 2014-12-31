#!/usr/bin/env python

#
# Copyright (C) 2014 Erwin Rieger
#

#
# Acknowledge of a usb transmission from printer:
#   One byte, Ascii-ACK (0x6)
#
#
# Compression:
#
# N5860 G1 F3000 X153.16 Y123.17 Z38.80 E459.21186*62 -> 51 bytes
# 
# 1 byte:            command key, 1-9
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
# Kompressed command keys:
# 
#   G0:  1   # xxx could be compressed as G1/2, see Marlin_main.cpp
#   G1:  2
#   G10: 3
#   G11: 4
# 


import sys, string, time, select, struct, argparse, collections

from serial import Serial, SerialException, PARITY_NONE


class Preprocessor:

    def __init__(self, mode, filename=None, gcode=[], stream=None):

        self.lineNr = 0
        self.origbytes = 0
        self.packbytes = 0
        self.uncompressedCmds = collections.defaultdict(int)

        # Always reset line counter first
        gcode = [("M110", "ok")] + gcode

        if filename or stream:

            # If in printing mode, then send custom M623 command,
            # select file for UM2 print
            if mode == "print":
                gcode += [("M623 usb.g", "ok")]

            # Store or print mode, open the file on the
            # SD card with the M28 command, then send the
            # contents of the file given on the commandline.
            # Close file on SD card with M29 if done.
            gcode += [("M28 usb.g", "ok")]

            if filename:
                inFile = open(filename)

                print "Preprocessing:", filename
                sys.stdout.flush()

                for line in inFile.readlines():
    
                    # Strip very long lines like ";CURA_PROFILE_STRING" line at the end of the file:
                    # Marlin: #define MAX_CMD_SIZE 96
                    if len(line) > 80:
                        continue

                    gcode.append((line, None))

            if filename:
                inFile.close()
            else:
                
                print "Preprocessing:", stream

                for line in stream:

                    # Strip very long lines like ";CURA_PROFILE_STRING" line at the end of the file:
                    # Marlin: #define MAX_CMD_SIZE 96
                    if len(line) > 80:
                        continue

                    gcode.append((line, None))

            gcode.append(("M29", Printer.endStoreToken))

        self.prep = self.preprocessGCode(gcode)

        # debug
        """
        if mode == "pre":
            print "saving to /tmp/usb.g"
            f = open("/tmp/usb.g", "w")
            lnr = 0
            for (cmd, resp) in self.prep:
                if isPackedCommand(cmd):
                    if lnr < 0x10000:
                        f.writelines(cmd[:-4] + "\n")
                    else:
                        f.writelines(cmd[:-6] + "\n")
                else:
                    n = cmd.split()[0]
                    c = cmd.split("*")[-1]
                    f.writelines(cmd[len(n)+1:-(len(c)+1)] + "\n")
                lnr += 1
            f.close()
        """

    def printStat(self):
        print "\n-----------------------------------------------"
        print "Preprocessor statistics:"
        print "-----------------------------------------------\n"
        print "Size of unpacked commands: %d bytes" % self.origbytes
        print "Size of   packed commands: %d bytes" % self.packbytes
        print "Compression ratio: %.1f%%" % (self.packbytes*100.0/self.origbytes)

        print "# Uncompressed commands: "
        for cmd in self.uncompressedCmds:
            print "%-10s: %5d" % (cmd, self.uncompressedCmds[cmd])


    # Create gcode checksum, this is stolen from
    # printrun/printcore.py ;-)
    def checksum(self, command):
        return reduce(lambda x, y: x ^ y, map(ord, command))

    def packGCode(self, code, lineNr):

        # Note: Arduino is little endian

        splitted = code.split()

        cmd = splitted[0]

        paramFlags = 0

        if cmd == "G0" or cmd == "G1":

            assert(len(splitted) <= 6)

            cmdHex = 1
            if cmd == "G1":
                cmdHex = 2

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

            chk = self.checksum(packed)
            packed += struct.pack("<B", chk)

            return packed + "\n"

        if cmd == "G10" or cmd == "G11":

            assert(len(splitted) == 1)

            cmdHex = 3
            if cmd == "G11":
                cmdHex = 4

            lnHex = struct.pack("<I", lineNr)
            if lineNr < 0x10000:
                # pack line number as short
                paramFlags += 1 << 2
                lnHex = struct.pack("<H", lineNr)

            packed = struct.pack("<BB", cmdHex, paramFlags)

            # add number and checksum
            packed += lnHex

            chk = self.checksum(packed)
            packed += struct.pack("<B", chk)

            return packed + "\n"

    def preprocessGCode(self, gcode):

        print "Preprocessing %d gcode lines..." % len(gcode)

        prep = []

        for (cmd, response) in gcode:

            scmd = cmd.strip()

            if not scmd:
                # skip empty lines
                continue

            if scmd == "M110":
                self.lineNr = 0

            prefix = "N" + str(self.lineNr) + " " + scmd
            chksm = self.checksum(prefix)

            # print scmd

            # Len of uncompressed command:
            #
            # + 1, "N"
            # + len("%d" % lineNr), linenumber
            # + 1, blank after linenumber
            # + len(cmd) 
            # + 1 + len(chksum), *<checksum>
            # + 1, newline
            #
            origlen = 1 + len("%d" % self.lineNr) + 1 + len(scmd) + 1 + len("%d" % chksm) + 1
            self.origbytes += origlen

            packed = self.packGCode(scmd, self.lineNr)

            if packed:

                self.packbytes += len(packed)

                prep.append( ( packed, response ) )
            else:

                self.packbytes += origlen

                if scmd[0] == ";":
                    self.uncompressedCmds["<comment>"] += 1
                else:
                    self.uncompressedCmds[scmd.split()[0]] += 1

                scmd = prefix + "*" + str(chksm) + "\n"

                # print "ll: ", len(scmd),  origlen
                # print "'%s'" % scmd
                assert(len(scmd) == origlen) # +1 is for newline

                prep.append( ( scmd, response ) )

            self.lineNr += 1

        print "done..."
        return prep

def isPackedCommand(cmd):
    return cmd[0] < "\n"


class SERIALDISCON(SerialException):
    pass

class Printer(Serial):

    endStoreToken = "Done saving"
    # Number of rx errors till we assume the
    # line is dead.
    maxRXErrors = 50

    def __init__(self, device, mode):
        Serial.__init__(
            self,
            port = device,
            # baudrate = 250000,
            # baudrate = 38400,
            baudrate = 115200,
            timeout = 0, parity = PARITY_NONE)

        if mode == "print":
            # self.endTokens = ["Done printing", 'echo:enqueing "M84"']   
            self.endTokens = ['echo:enqueing "M84"']   
        else:
            self.endTokens = [self.endStoreToken, 'echo:enqueing "M84"']

        self.mode = mode
        self.cmdIndex = 0
        self.lastSend = 0

        # Retry counter on rx errors
        self.rxErrors = 0

    # Check a printer response for an error
    def checkError(self, recvLine):

        if "Error:" in recvLine and  "Last Line" in recvLine:
            # Error:Line Number is not Last Line Number+1, Last Line: 9            
            # Error:checksum mismatch, Last Line: 71388
            lastLine = int(recvLine.split(":")[2])

            print "\nERROR:"
            print "Reply: ", recvLine,
            print "Scheduling resend of command:", lastLine+1

            # assert(self.cmdIndex == lastLine + 2)

            self.cmdIndex = lastLine + 1

            # Wait 0.1 sec, give firmware time to drain buffers
            time.sleep(0.5)
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
    def safeReadline(self):

        result = ""

        while True:
            try:
                c = self.read()
                # print "c: ", c
            except SerialException as ex:
                if self.rxErrors < 5:
                    print "Readline() Exception raised:", ex

                self.rxErrors += 1

                if self.rxErrors >= Printer.maxRXErrors:
                    print "declare line is dead ..."
                    raise SERIALDISCON

                time.sleep(0.1)
                break

            if not c:
                break

            # Received something, reset error counter
            self.rxErrors = 0

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

            if readable:
                try:
                    recvLine = self.safeReadline()        
                except SERIALDISCON:
                    print "Line disconnected in readMore"
                    return

                if recvLine:
                    if ord(recvLine[0]) > 20:
                        print "Reply: ", recvLine,
                    else:
                        print "Reply: 0x%s" % recvLine.encode("hex")
                    sys.stdout.flush()

    # Stop and reset the printer
    def reset(self):

        print "\nResetting printer"

        # self._send("M29\n") # End sd write, response: "Done saving"
        # self._send("G28\n") # Home all Axis, response: ok
        # self._send("M84\n") # Disable steppers until next move, response: ok
        # self._send("M104 S0\n") # Set temp
        # self._send("M140 S0\n") # Set temp

        gcode = ["M29", "G28", "M84", "M104 S0", "M140 S0"]
        prep = Preprocessor("reset", gcode = map(lambda x: (x, None), gcode))

        print "Reset code sequence: ", prep.prep

        for (cmd, resp) in prep.prep:
            self.send(cmd)
            self.readMore(5)

        self.readMore(50)

    # Send a command to the printer, add a newline if 
    # needed.
    def send(self, cmd):

        assert(cmd[-1] == "\n")

        if isPackedCommand(cmd):
        
            print "\nSend: ", cmd.encode("hex")
            sys.stdout.flush()
            self._send(cmd)
        else:

            print "\nSend: ", cmd,
            sys.stdout.flush()
            self._send(cmd)

    # Send a command to the printer
    def _send(self, cmd):

        self.write(cmd)


    # The 'mainloop' process each command in the list 'gcode', check
    # for the required responses and do errorhandling.
    def sendGcode(self, gcode, wantReply=None, waitForEndReply=True):

        startTime = time.time()

        self.cmdIndex = 0

        recvPart = None

        wantAck = False

        while True:

            if not wantAck and not wantReply and self.mode != "mon" and self.cmdIndex < len(gcode):
                # send a line
                (line, wantReply) = gcode[self.cmdIndex]
                self.send(line)
                self.cmdIndex += 1
                self.lastSend = time.time()
                wantAck = True

            readable, writable, exceptional = select.select([self], [], [], 0.1)

            if exceptional:
                print "exception on select: ", exceptional
                self.reset()
                print "\n\nPrinter reset done, bailing out...\n\n"
                assert(0)

            if not readable:
                continue

            recvLine = self.safeReadline()        

            if not recvLine:
                continue

            # print "R0:", ord(recvLine[0])

            if recvPart:
                recvLine = recvPart + recvLine
                recvPart = None

            if recvLine[-1] != "\n":
                recvPart = recvLine
                continue

            if self.mode != "mon" and self.checkError(recvLine):
                # command resend
                wantAck = False
                wantReply = None
                continue

            if wantAck and recvLine[0] == chr(0x6):
                print "ACK"
                wantAck = False
                sys.stdout.flush()
                continue

            if wantReply and recvLine.startswith(wantReply):
                print "Got Required reply: ", recvLine,
                wantReply = None
            else:
                print "Reply: ", recvLine,

            if recvLine.startswith(self.endStoreToken):
                print "\n-----------------------------------------------"
                print "Store statistics:"
                print "-----------------------------------------------\n"
                duration = time.time() - startTime
                print "Sent %d commands in %.1f seconds, %.1f commands/second.\n" % (len(gcode), duration, len(gcode)/duration)

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
# Main
#
if __name__ == "__main__":

    parser = argparse.ArgumentParser(description='UltiPrint, print on UM2 over USB.')
    parser.add_argument("-d", dest="device", action="store", type=str, help="Device to use, default: /dev/ttyACM0.", default="/dev/ttyACM0")

    subparsers = parser.add_subparsers(dest="mode", help='Mode: mon(itor)|print|store|reset|pre(process).')

    sp = subparsers.add_parser("mon", help=u"Monitor printer.")

    sp = subparsers.add_parser("print", help=u"Print file.")
    sp.add_argument("gfile", help="Input GCode file.")

    sp = subparsers.add_parser("store", help=u"Store file as USB.G on sd-card.")
    sp.add_argument("gfile", help="Input GCode file.")

    sp = subparsers.add_parser("reset", help=u"Try to stop/reset printer.")

    sp = subparsers.add_parser("pre", help=u"Preprocess gcode, for debugging purpose.")
    sp.add_argument("gfile", help="Input GCode file.")

    args = parser.parse_args()
    # print "args: ", args

    if args.mode == 'pre':
        #
        # Preprocess only
        #
        prep = Preprocessor(args.mode, args.gfile)
        prep.printStat();
        sys.exit(0)

    printer = Printer(args.device, args.mode)

    # Read left over garbage
    recvLine = printer.safeReadline()        
    print "Initial read: "
    print recvLine.encode("hex"), "\n"

    if args.mode == "reset":
        #
        # Reset printer
        #
        printer.reset()
        sys.exit(0)

    if args.mode == "mon":
        #
        # Monitor printer output
        #
        printer.sendGcode([], "echo:SD card ok")
        sys.exit(0)


    prep = Preprocessor(args.mode, args.gfile)

    try:
        printer.sendGcode(prep.prep, "echo:SD card ok")
    except SERIALDISCON:
        print "Line disconnected in sendGcode(). Can't do a reset! Check your printer!"
        sys.exit(1)


    prep.printStat();






