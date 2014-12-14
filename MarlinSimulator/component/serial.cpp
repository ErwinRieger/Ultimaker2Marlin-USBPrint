#include <avr/io.h>
#include <string.h>
#include <assert.h>

/* 
#include <iostream>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <stdlib.h>
#include <pthread.h>
#include <termios.h>
*/
#include <unistd.h>
#include <fcntl.h>


#include "serial.h"

serialSim::serialSim()
{

    UCSR0A.setCallback(DELEGATE(registerDelegate, serialSim, *this, UART_UCSR0A_callback));
    UDR0.setCallback(DELEGATE(registerDelegate, serialSim, *this, UART_UDR0_callback));

    UCSR0A.setReadCallback(RDELEGATE(registerRDelegate, serialSim, *this, UART_UCSR0A_read_callback));
    UDR0.setReadCallback(RDELEGATE(registerRDelegate, serialSim, *this, UART_UDR0_read_callback));

    UCSR0A = 0;
    
    recvLine = 0;
    recvPos = 0;
    memset(recvBuffer, '\0', sizeof(recvBuffer));

    ptty = open("/dev/ptmx", O_RDWR | O_NOCTTY | O_NONBLOCK);
    if (ptty == -1) {
        printf("error opening /dev/ptmx\n");
        return;
    }

    grantpt(ptty);
    unlockpt(ptty);

    const char* pts_name = ptsname(ptty);
    assert(pts_name);

    printf("ptsname: %s, sleeping 10 seconds ...\n", pts_name);
    sleep(10);
}

serialSim::~serialSim()
{
}


void serialSim::UART_UCSR0A_callback(uint8_t oldValue, uint8_t& newValue)
{
    //Always mark "write ready" flag, so the serial code never waits.
    newValue |= _BV(UDRE0);
}

uint8_t  serialSim::UART_UCSR0A_read_callback(uint8_t& value)
{

   if (((value & _BV(RXC0)) == 0) && (ptty >= 0) && (read(ptty, &rxChar, 1) == 1)) {

        // printf("UART_UCSR0A_read_callback read: %c\n", rxChar);
        value |= _BV(RXC0);
   }

   return value;
}

void serialSim::UART_UDR0_callback(uint8_t oldValue, uint8_t& newValue)
{
    recvBuffer[recvLine][recvPos] = newValue;
    recvPos++;
    if (recvPos == 80 || newValue == '\n')
    {
        recvPos = 0;
        recvLine++;
        if (recvLine == SERIAL_LINE_COUNT)
        {
            for(unsigned int n=0; n<SERIAL_LINE_COUNT-1;n++)
                memcpy(recvBuffer[n], recvBuffer[n+1], 80);
            recvLine--;
            memset(recvBuffer[recvLine], '\0', 80);
        }
    }

    write(ptty, &newValue, 1);
}

uint8_t  serialSim::UART_UDR0_read_callback(uint8_t& value)
{

    // printf("UART_UDR0_read_callback: %c\n", rxChar);

    uint8_t c = rxChar;

    if (read(ptty, &rxChar, 1) <= 0) {
        UCSR0A &= ~_BV(RXC0);
    }

    return c;
}

void serialSim::draw(int x, int y)
{
    for(unsigned int n=0; n<SERIAL_LINE_COUNT;n++)
        drawStringSmall(x, y+n*3, recvBuffer[n], 0xFFFFFF);
}

