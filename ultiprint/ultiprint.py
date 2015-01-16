#!/usr/bin/env python

# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

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
# 1 byte:           'parameter mask', bits: FXYZES00 (2 unused bits)
# 2 bytes:           F param
# 4 bytes:           X param
# 4 bytes:           Y param
# 4 bytes:           Z param
# 4 bytes:           E param
# 2/4 bytes:         2 or 4byte line counter, am schluss, damit einfach abzuschneiden
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

from serial import Serial, SerialException, PARITY_NONE, TERMIOS, TIOCMBIS, TIOCMBIC, TIOCM_RTS_str, TIOCM_DTR_str, TIOCM_DTR, TIOCM_RTS

# # This needs pyserial version >= 2.6:
# try:
    # from serial.tools import list_ports
# except ImportError:
    # print "\nWARNING your python-serial version seems to be to old!\n"

#
# Note: pyserial 2.6.1 seems to have a bug with reconnect (read only garbage 
# at second connect).
# So i've mixed pyserial 2.5.x with the list_ports functions from 2.6.x
#
import list_ports

# >>> list_ports.comports()
# [('/dev/ttyS3', 'ttyS3', 'n/a'),
#('/dev/ttyS2', 'ttyS2', 'n/a'),
#('/dev/ttyS1', 'ttyS1', 'PNP0501'),
#('/dev/ttyS0', 'ttyS0', 'PNP0501'),
#('/dev/ttyUSB10', 'ttyUSB10', 'n/a'),
#('/dev/ttyUSB0', 'Linux Foundation 2.0 root hub ', 'USB VID:PID=0403:f06f SNR=ELU2CSFC'),
#('/dev/ttyACM0', 'ttyACM0', 'USB VID:PID=2341:0042 SNR=75237333536351815111')]

class DummyEvent:

    def RequestMore(self, b):
        pass

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
    maxRXErrors = 10

    def __init__(self):

        Serial.__init__(self)

        self.usbId = None

        self.mode = None
        self.endTokens = None
        self.lastSend = 0

        self.gcodeData = []
        self.gcodePos = 0

        # Retry counter on rx errors
        self.rxErrors = 0

        # Timespan where we monitor the serial line after the
        # print has finished.
        self.postMonitor = 0

        self.printing = False

        self.startTime = None

        self.wantReply = None
        self.wantAck = None
        # Part of a response read from printer
        self.recvPart = ""

    def initMode(self, mode):

        self.mode = mode

        self.endTokens = ['echo:enqueing "M84"']   
            
    def initSerial(self, device, br=115200):
        self.port = device
        self.baudrate = br
        self.timeout = 0.05
        self.writeTimeout = 10
        self.open()

        # Store usb information for later re-connection even if device
        # name has changed:
        comports = list_ports.comports()

        # ('/dev/ttyACM0', 'ttyACM0', 'USB VID:PID=2341:0042 SNR=75237333536351815111')]
        for (dev, name, usbid) in comports:
            if dev == device or name == device:
                print "Found usbid %s for device %s" % (usbid, dev)
                self.usbId = usbid
                break
        
    def reconnect(self):

        # XXX add timeout, or otherwise prevent re-connection to power-cycled printer?!

        comports = list_ports.comports()

        # ('/dev/ttyACM0', 'ttyACM0', 'USB VID:PID=2341:0042 SNR=75237333536351815111')]
        for (dev, name, usbid) in comports:
            if usbid == self.usbId:
                print "reconnect(): found device %s, previous device: %s" % (dev, self.port)
                self.close()
                self.initSerial(dev, br=self.baudrate)
                return

        time.sleep(0.1)

    def showMessage(self, s):
        print s

    def showError(self, s):
        print "\n%s" %s

    # Check a printer response for an error
    def checkError(self, recvLine):

        if "Error:" in recvLine and  "Last Line" in recvLine:
            # Error:Line Number is not Last Line Number+1, Last Line: 9            
            # Error:checksum mismatch, Last Line: 71388
            lastLine = int(recvLine.split(":")[2])

            print "\nERROR:"
            print "Reply: ", recvLine,
            print "Scheduling resend of command:", lastLine+1

            # assert(self.gcodePos == lastLine + 2)

            self.gcodePos = lastLine + 1

            # Wait 0.1 sec, give firmware time to drain buffers
            time.sleep(0.5)
            return True

        for token in ["Error:", "cold extrusion", "SD init fail", "open failed"]:
            if token in recvLine:

                self.printing = False

                s = "ERROR: reply from printer: '%s'" % recvLine
                self.showError(s)

                # print "\nERROR:"
                # print "Reply: ", recvLine,
                # sys.stdout.flush()
                # self.readMore(20)

                self.reset()

                # print "\n\nPrinter reset done, bailing out...\n\n"
                # assert(0)

    # Read a response from printer, "handle" exceptions
    def safeReadline(self):

        result = ""

        while True:
            try:
                c = self.read()
                # print "c: ", c
            except SerialException as ex:
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

        print "waiting %.2f seconds for more messages..." % (waitcount/20.0)

        for i in range(waitcount):

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

    # Stop and reset the printer
    # xxx does not work right yet, um2 display still says 'preheating...'
    # yyy is this still the case?
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

    # Send a command to the printer, add a newline if 
    # needed.
    def send(self, cmd):

        if isPackedCommand(cmd):
        
            print "\nSend: ", cmd.encode("hex")
            self.write(cmd)
        else:

            print "\nSend: ", cmd,
            self.write(cmd)


    # The 'mainloop' process each command in the list 'gcode', check
    # for the required responses and do errorhandling.
    def sendGcode(self, gcode, wantReply=None):

        self.printing = True

        self.startTime = time.time()

        self.gcodeData = gcode
        self.gcodePos = 0

        self.wantReply = wantReply
        self.wantAck = False

        self.recvPart = None

        ev = DummyEvent()

        while self.processCommand(ev):
            pass

    def processCommand(self, ev):

        if not self.printing and time.time() > self.postMonitor:
            return False

        # if time.time() <  self.postMonitor: 
            # print "postmon: ", self.wantAck, self.wantReply, self.gcodePos
        
        # if self.printing:
            # print "print: ", self.wantAck, self.wantReply, self.gcodePos

        if self.printing and not self.wantAck and not self.wantReply and self.mode != "mon" and self.gcodePos < len(self.gcodeData):
            # send a line
            (line, self.wantReply) = self.gcodeData[self.gcodePos]
            self.send(line)
            self.gcodePos += 1
            self.lastSend = time.time()
            self.wantAck = True

            # Update gui
            if (self.gcodePos % 250) == 0:
                duration = time.time() - self.startTime
                self.showMessage("Sent %d/%d gcodes, %.1f gcodes/sec" % (self.gcodePos, len(self.gcodeData), self.gcodePos/duration))

            # We have sent a command to the printer, request more
            # cpu cycles from wx to process the answer quickly
            ev.RequestMore(True)

        try:
            recvLine = self.safeReadline()        
        except SERIALDISCON:
            # self.printing = False
            # self.postMonitor = 0
            # self.showError("Line disconnected in processCommand(). Can't do a reset! Check your printer!")
            self.showError("Line disconnected in processCommand(). Trying reconnect!")
            self.reconnect()
            return True

        if not recvLine:
            return True

        # There was something to read, so request more
        # cpu cycles from wx
        ev.RequestMore(True)


        if self.recvPart:
            recvLine = self.recvPart + recvLine
            self.recvPart = None

        if recvLine[-1] != "\n":
            self.recvPart = recvLine
            return True

        if self.mode != "mon" and self.checkError(recvLine):
            # command resend
            self.wantAck = False
            self.wantReply = None
            return True

        if self.wantAck and recvLine[0] == chr(0x6):
            print "ACK"
            self.wantAck = False
            return True

        if self.wantReply and recvLine.startswith(self.wantReply):
            print "Got Required reply: ", recvLine,
            self.wantReply = None
        else:
            print "Reply: ", recvLine,

        # self.endTokens = ['echo:enqueing "M84"']   

        if recvLine.startswith(self.endStoreToken):

            self.postMonitor = time.time() + 5

            print "\n-----------------------------------------------"
            print "Store statistics:"
            print "-----------------------------------------------\n"
            self.storeDuration = time.time() - self.startTime

            if self.mode == "store":
                self.showMessage("Sent %d gcodes in %.1f seconds, %.1f gcodes/sec." % (self.gcodePos, self.storeDuration, self.gcodePos/self.storeDuration))
                self.printing = False
            else:
                self.showMessage("Sent %d gcodes in %.1f seconds, %.1f gcodes/sec.\nPlease wait for the print to finish.\n" % (self.gcodePos, self.storeDuration, self.gcodePos/self.storeDuration))

        else:

            for token in self.endTokens:
                if recvLine.startswith(token):

                    self.postMonitor = time.time() + 5

                    print "end-reply received, finished print..."
                    self.printing = False

                    duration = time.time() - self.startTime

                    self.showMessage("Print finished. Duration: %.1f seconds, Downloadspeed: %.1f gcodes/sec.\n" % (duration, self.gcodePos/self.storeDuration))

        return True

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

    printer = Printer()
    printer.initMode(args.mode)
    printer.initSerial(args.device)

    # Read left over garbage
    recvLine = printer.safeReadline()        
    print "Initial read: "
    print recvLine.encode("hex"), "\n"

    if args.mode == "reset":
        #
        # Reset printer
        #
        printer.reset()
        printer.readMore(50)
        sys.exit(0)

    if args.mode == "mon":
        #
        # Monitor printer output
        #
        printer.sendGcode([], "echo:SD card ok")
        sys.exit(0)


    prep = Preprocessor(args.mode, args.gfile)

    printer.sendGcode(prep.prep, "echo:SD card ok")


    prep.printStat();






