#ifndef SERIAL_SIM_H
#define SERIAL_SIM_H

#include "base.h"

#define SERIAL_LINE_COUNT 30
class serialSim : public simBaseComponent
{
public:
    serialSim();
    virtual ~serialSim();
    
    virtual void draw(int x, int y);

private:
    int recvLine, recvPos;
    char recvBuffer[SERIAL_LINE_COUNT][80];
   
    // Filedescriptor for serial pseudo tty 
    int ptty;
    // Character received from serial pseudo tty 
    uint8_t rxChar;

    void UART_UCSR0A_callback(uint8_t oldValue, uint8_t& newValue);
    void UART_UDR0_callback(uint8_t oldValue, uint8_t& newValue);
    uint8_t  UART_UCSR0A_read_callback(uint8_t& value);
    uint8_t  UART_UDR0_read_callback(uint8_t& value);
};

#endif//SERIAL_SIM_H
