/*
    Copyright (C) 2014 Erwin Rieger for UltiGCode USB store and
    print modifications.
*/
#ifndef CARDREADER_H
#define CARDREADER_H

#ifdef SDSUPPORT

#define MAX_DIR_DEPTH 10

#if (SDCARDDETECT > -1)
# ifdef SDCARDDETECTINVERTED
#  define IS_SD_INSERTED (READ(SDCARDDETECT)!=0)
# else
#  define IS_SD_INSERTED (READ(SDCARDDETECT)==0)
# endif //SDCARDTETECTINVERTED
#else
//If we don't have a card detect line, aways asume the card is inserted
# define IS_SD_INSERTED true
#endif

#include "SdFile.h"
enum LsAction {LS_SerialPrint,LS_Count,LS_GetFilename};
class CardReader
{
public:
  CardReader();

  void initsd();
  void write_command(char *buf);
  bool write_string(char* buffer);
  //files auto[0-9].g on the sd card are performed in a row
  //this is to delay autostart and hence the initialisaiton of the sd card to some seconds after the normal init, so the device is available quick after a reset

  void checkautostart(bool x);
  void openFile(const char* name,bool read);
  void openLogFile(const char* name);
  void removeFile(const char* name);
  void closefile();
  void release();
  void startFileprint();
  void pauseSDPrint();
  void getStatus();
  void printingHasFinished();

  void getfilename(const uint8_t nr);
  uint16_t getnrfilenames();


  void ls();
  void chdir(const char * relpath);
  void updir();
  void setroot();


  FORCE_INLINE bool isFileOpen() { return file.isOpen(); }
  FORCE_INLINE bool eof() { return sdReadPos >= getFileSize() ;};
  FORCE_INLINE int16_t get() {
      // sdReadPos  = file.curPosition();return (int16_t)file.read();
      file.seekSet(sdReadPos);
      int16_t c = file.read();
      if (c != -1)
        sdReadPos++;
      return c; }

  FORCE_INLINE int16_t fgets(char* str, int16_t num) {
    if (! file.seekSet(sdReadPos)) 
      MYSERIAL.print("fgets: can't seek\n");

    int16_t readbytes = file.fgets(str, num, NULL);
    sdReadPos += readbytes;
    return readbytes;
   }

  FORCE_INLINE void setReadFilePos(long index) {sdReadPos  = index; /* file.seekSet(index); */};
  FORCE_INLINE uint8_t percentDone(){if(!isFileOpen()) return 0; if(getFileSize()) return sdReadPos /((getFileSize()+99)/100); else return 0;};
  FORCE_INLINE char* getWorkDirName(){workDir.getFilename(filename);return filename;};
  FORCE_INLINE bool atRoot() { return workDirDepth==0; }
  FORCE_INLINE uint32_t getReadFilePos() { return sdReadPos ; }
  FORCE_INLINE uint32_t getFileSize() { return file.fileSize(); }
  FORCE_INLINE bool isOk() { return cardOK && card.errorCode() == 0; }
  FORCE_INLINE int errorCode() { return card.errorCode(); }
  FORCE_INLINE void clearError() { card.error(0); }
  FORCE_INLINE void updateSDInserted()
  {
    bool newInserted = IS_SD_INSERTED;
    if (sdInserted != newInserted)
    {
      if (insertChangeDelay)
        insertChangeDelay--;
      else
        sdInserted = newInserted;
    }else{
      insertChangeDelay = 1000 / 25;
    }
  }
  FORCE_INLINE uint8_t getOpenCount() { return opencount; }
  FORCE_INLINE bool isSaving() { return saving; }
  void endSaving();

public:
  bool logging;
  bool sdprinting;
  bool pause;
  bool sdInserted;
  char filename[13];
  char longFilename[LONG_FILENAME_LENGTH];
  bool filenameIsDir;
  int lastnr; //last number of the autostart;
private:
  bool cardOK;
  SdFile root,*curDir,workDir,workDirParents[MAX_DIR_DEPTH];
  uint8_t workDirDepth;
  uint8_t insertChangeDelay;
  Sd2Card card;
  SdVolume volume;
  SdFile file;
  //int16_t n;
  unsigned long autostart_atmillis;
  uint32_t sdReadPos  ;

  bool autostart_stilltocheck; //the sd start is delayed, because otherwise the serial cannot answer fast enought to make contact with the hostsoftware.

  LsAction lsAction; //stored for recursion.
  int16_t nrFiles; //counter for the files in the current directory and recycled as position counter for getting the nrFiles'th name in the directory.
  char* diveDirName;
  void lsDive(const char *prepend,SdFile parent);
  // Number of open calls minus number of close calls
  uint8_t opencount;
  bool saving;
};
extern CardReader card;
#define IS_SD_PRINTING (card.sdprinting)

#else

#define IS_SD_PRINTING (false)

#endif //SDSUPPORT
#endif
