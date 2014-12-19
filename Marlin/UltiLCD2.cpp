/*
    Copyright (C) 2014 Erwin Rieger for UltiGCode USB store and
    print modifications.
*/
#include "Configuration.h"
#ifdef ENABLE_ULTILCD2
#include "UltiLCD2.h"
#include "UltiLCD2_hi_lib.h"
#include "UltiLCD2_gfx.h"
#include "UltiLCD2_menu_material.h"
#include "UltiLCD2_menu_print.h"
#include "UltiLCD2_menu_first_run.h"
#include "UltiLCD2_menu_maintenance.h"
#include "cardreader.h"
#include "ConfigurationStore.h"
#include "temperature.h"
#include "pins.h"

#define SERIAL_CONTROL_TIMEOUT 5000

unsigned long lastSerialCommandTime;
bool serialScreenShown;

// Print start over serial/usb
static unsigned long lastStartCheck;
// Filename in 8.3 format, written by Marlin_main.cpp:process_commands(), serial
// command 'M623'.
char fnAutoPrint[13] = { '\0' };

uint8_t led_brightness_level = 100;
uint8_t led_mode = LED_MODE_ALWAYS_ON;

//#define SPECIAL_STARTUP

static void lcd_menu_startup();
#ifdef SPECIAL_STARTUP
static void lcd_menu_special_startup();
#endif//SPECIAL_STARTUP

static void lcd_menu_breakout();

static void lcd_menu_autoStart();

void lcd_init()
{
    lcd_lib_init();
    if (!lcd_material_verify_material_settings())
    {
        lcd_material_reset_defaults();
        for(uint8_t e=0; e<EXTRUDERS; e++)
            lcd_material_set_material(0, e);
    }
    lcd_material_read_current_material();
    currentMenu = lcd_menu_startup;
    analogWrite(LED_PIN, 0);
    lastSerialCommandTime = millis() - SERIAL_CONTROL_TIMEOUT;
}

void lcd_update()
{

    if (!lcd_lib_update_ready()) return;
    lcd_lib_buttons_update();
    card.updateSDInserted();

    if (led_glow_dir)
    {
        led_glow-=2;
        if (led_glow == 0) led_glow_dir = 0;
    }else{
        led_glow+=2;
        if (led_glow == 126) led_glow_dir = 1;
    }

    if (IsStopped())
    {
        lcd_lib_clear();
        lcd_lib_draw_string_centerP(10, PSTR("ERROR - STOPPED"));
        switch(StoppedReason())
        {
        case STOP_REASON_MAXTEMP:
        case STOP_REASON_MINTEMP:
            lcd_lib_draw_string_centerP(20, PSTR("Temp sensor"));
            break;
        case STOP_REASON_MAXTEMP_BED:
            lcd_lib_draw_string_centerP(20, PSTR("Temp sensor BED"));
            break;
        case STOP_REASON_HEATER_ERROR:
            lcd_lib_draw_string_centerP(20, PSTR("Heater error"));
            break;
        case STOP_REASON_SAFETY_TRIGGER:
            lcd_lib_draw_string_centerP(20, PSTR("Safety circuit"));
            break;
        case STOP_REASON_Z_ENDSTOP_BROKEN_ERROR:
            lcd_lib_draw_string_centerP(20, PSTR("Z switch broken"));
            break;
        case STOP_REASON_Z_ENDSTOP_STUCK_ERROR:
            lcd_lib_draw_string_centerP(20, PSTR("Z switch stuck"));
            break;
        case STOP_REASON_XY_ENDSTOP_BROKEN_ERROR:
            lcd_lib_draw_string_centerP(20, PSTR("X or Y switch broken"));
            break;
        case STOP_REASON_XY_ENDSTOP_STUCK_ERROR:
            lcd_lib_draw_string_centerP(20, PSTR("X or Y switch stuck"));
            break;
        }
        lcd_lib_draw_stringP(1, 40, PSTR("Contact:"));
        lcd_lib_draw_stringP(1, 50, PSTR( "support@ultimaker.com" ));
        LED_GLOW_ERROR();
        lcd_lib_update_screen();
    }
    // Check autoprint variable if a file should be printed (M623 command)
    else if (
        (fnAutoPrint[0] != '\0') && 
        card.sdInserted && 
        (currentMenu == lcd_menu_main))
    {

        // Prepare for usb-print, wait 10 seconds
        lastStartCheck = millis();

        lcd_change_to_menu(lcd_menu_autoStart);
    }
    else if (millis() - lastSerialCommandTime < SERIAL_CONTROL_TIMEOUT)
    {
        if (!serialScreenShown)
        {
            lcd_lib_clear();
            lcd_lib_draw_string_centerP(20, PSTR("Printing with USB..."));
            serialScreenShown = true;
        }
        if (printing_state == PRINT_STATE_HEATING || printing_state == PRINT_STATE_HEATING_BED || printing_state == PRINT_STATE_HOMING)
            lastSerialCommandTime = millis();
        lcd_lib_update_screen();
    }else{
        serialScreenShown = false;
        currentMenu();
        if (postMenuCheck) postMenuCheck();
    }
}

void lcd_menu_startup()
{
    lcd_lib_encoder_pos = ENCODER_NO_SELECTION;

    LED_GLOW();
    lcd_lib_clear();

    if (led_glow < 84)
    {
        lcd_lib_draw_gfx(0, 22, ultimakerTextGfx);
        for(uint8_t n=0;n<10;n++)
        {
            if (led_glow*2 >= n + 20)
                lcd_lib_clear(0, 22+n*2, led_glow*2-n-20, 23+n*2);
            if (led_glow*2 >= n)
                lcd_lib_clear(led_glow*2 - n, 22+n*2, 127, 23+n*2);
            else
                lcd_lib_clear(0, 22+n*2, 127, 23+n*2);
        }
    /*
    }else if (led_glow < 86) {
        led_glow--;
        //lcd_lib_set();
        //lcd_lib_clear_gfx(0, 22, ultimakerTextGfx);
        lcd_lib_draw_gfx(0, 22, ultimakerTextGfx);
    */
    }else{
        led_glow--;
        //lcd_lib_draw_gfx(80, 0, ultimakerRobotGfx);
        //lcd_lib_clear_gfx(0, 22, ultimakerTextOutlineGfx);
        lcd_lib_draw_gfx(0, 22, ultimakerTextGfx);
    }
    lcd_lib_update_screen();

    if (led_mode == LED_MODE_ALWAYS_ON)
        analogWrite(LED_PIN, int(led_glow << 1) * led_brightness_level / 100);
    if (led_glow_dir || lcd_lib_button_pressed)
    {
        if (led_mode == LED_MODE_ALWAYS_ON)
            analogWrite(LED_PIN, 255 * led_brightness_level / 100);
        led_glow = led_glow_dir = 0;
        LED_NORMAL();
        if (lcd_lib_button_pressed)
            lcd_lib_beep();

#ifdef SPECIAL_STARTUP
        currentMenu = lcd_menu_special_startup;
#else
        if (!IS_FIRST_RUN_DONE())
        {
            currentMenu = lcd_menu_first_run_init;
        }else{
            currentMenu = lcd_menu_main;
        }
#endif//SPECIAL_STARTUP
    }
}

#ifdef SPECIAL_STARTUP
static void lcd_menu_special_startup()
{
    LED_GLOW();

    lcd_lib_clear();
    lcd_lib_draw_gfx(7, 12, specialStartupGfx);
    lcd_lib_draw_stringP(3, 2, PSTR("Welcome"));
    lcd_lib_draw_string_centerP(47, PSTR("To the Ultimaker2"));
    lcd_lib_draw_string_centerP(55, PSTR("experience!"));
    lcd_lib_update_screen();

    if (lcd_lib_button_pressed)
    {
        if (!IS_FIRST_RUN_DONE())
        {
            lcd_change_to_menu(lcd_menu_first_run_init);
        }else{
            lcd_change_to_menu(lcd_menu_main);
        }
    }
}
#endif//SPECIAL_STARTUP

void doCooldown()
{
    for(uint8_t n=0; n<EXTRUDERS; n++)
        setTargetHotend(0, n);
    setTargetBed(0);
    fanSpeed = 0;

    //quickStop();         //Abort all moves already in the planner
}

void lcd_menu_main()
{
    lcd_tripple_menu(PSTR("PRINT"), PSTR("MATERIAL"), PSTR("MAINTENANCE"));

    if (lcd_lib_button_pressed)
    {
        if (IS_SELECTED_MAIN(0))
        {
            lcd_clear_cache();
            card.release();
            lcd_change_to_menu(lcd_menu_print_select, SCROLL_MENU_ITEM_POS(0));
        }
        else if (IS_SELECTED_MAIN(1))
            lcd_change_to_menu(lcd_menu_material);
        else if (IS_SELECTED_MAIN(2))
            lcd_change_to_menu(lcd_menu_maintenance);
    }
    if (lcd_lib_button_down && lcd_lib_encoder_pos == ENCODER_NO_SELECTION)
    {
        led_glow_dir = 0;
        if (led_glow > 200)
            lcd_change_to_menu(lcd_menu_breakout);
    }else{
        led_glow = led_glow_dir = 0;
    }

    lcd_lib_update_screen();
}


#define BREAKOUT_PADDLE_WIDTH 21
//Use the lcd_cache memory to store breakout data, so we do not waste memory.
#define ball_x (*(int16_t*)&lcd_cache[3*5])
#define ball_y (*(int16_t*)&lcd_cache[3*5+2])
#define ball_dx (*(int16_t*)&lcd_cache[3*5+4])
#define ball_dy (*(int16_t*)&lcd_cache[3*5+6])
static void lcd_menu_breakout()
{
    if (lcd_lib_encoder_pos == ENCODER_NO_SELECTION)
    {
        lcd_lib_encoder_pos = (128 - BREAKOUT_PADDLE_WIDTH) / 2 / 2;
        for(uint8_t y=0; y<3;y++)
            for(uint8_t x=0; x<5;x++)
                lcd_cache[x+y*5] = 3;
        ball_x = 0;
        ball_y = 57 << 8;
        ball_dx = 0;
        ball_dy = 0;
    }

    if (lcd_lib_encoder_pos < 0) lcd_lib_encoder_pos = 0;
    if (lcd_lib_encoder_pos * 2 > 128 - BREAKOUT_PADDLE_WIDTH - 1) lcd_lib_encoder_pos = (128 - BREAKOUT_PADDLE_WIDTH - 1) / 2;
    ball_x += ball_dx;
    ball_y += ball_dy;
    if (ball_x < 1 << 8) ball_dx = abs(ball_dx);
    if (ball_x > 124 << 8) ball_dx = -abs(ball_dx);
    if (ball_y < (1 << 8)) ball_dy = abs(ball_dy);
    if (ball_y < (3 * 10) << 8)
    {
        uint8_t x = (ball_x >> 8) / 25;
        uint8_t y = (ball_y >> 8) / 10;
        if (lcd_cache[x+y*5])
        {
            lcd_cache[x+y*5]--;
            ball_dy = abs(ball_dy);
            for(y=0; y<3;y++)
            {
                for(x=0; x<5;x++)
                    if (lcd_cache[x+y*5])
                        break;
                if (x != 5)
                    break;
            }
            if (x==5 && y==3)
            {
                for(y=0; y<3;y++)
                    for(x=0; x<5;x++)
                        lcd_cache[x+y*5] = 3;
            }
        }
    }
    if (ball_y > (58 << 8))
    {
        if (ball_x < (lcd_lib_encoder_pos * 2 - 2) << 8 || ball_x > (lcd_lib_encoder_pos * 2 + BREAKOUT_PADDLE_WIDTH) << 8)
            lcd_change_to_menu(lcd_menu_main);
        ball_dx += (ball_x - ((lcd_lib_encoder_pos * 2 + BREAKOUT_PADDLE_WIDTH / 2) * 256)) / 64;
        ball_dy = -512 + abs(ball_dx);
    }
    if (ball_dy == 0)
    {
        ball_y = 57 << 8;
        ball_x = (lcd_lib_encoder_pos * 2 + BREAKOUT_PADDLE_WIDTH / 2) << 8;
        if (lcd_lib_button_pressed)
        {
            ball_dx = -256 + lcd_lib_encoder_pos * 8;
            ball_dy = -512 + abs(ball_dx);
        }
    }

    lcd_lib_clear();

    for(uint8_t y=0; y<3;y++)
        for(uint8_t x=0; x<5;x++)
        {
            if (lcd_cache[x+y*5])
                lcd_lib_draw_box(3 + x*25, 2 + y * 10, 23 + x*25, 10 + y * 10);
            if (lcd_cache[x+y*5] == 2)
                lcd_lib_draw_shade(4 + x*25, 3 + y * 10, 22 + x*25, 9 + y * 10);
            if (lcd_cache[x+y*5] == 3)
                lcd_lib_set(4 + x*25, 3 + y * 10, 22 + x*25, 9 + y * 10);
        }

    lcd_lib_draw_box(ball_x >> 8, ball_y >> 8, (ball_x >> 8) + 2, (ball_y >> 8) + 2);
    lcd_lib_draw_box(lcd_lib_encoder_pos * 2, 60, lcd_lib_encoder_pos * 2 + BREAKOUT_PADDLE_WIDTH, 63);
    lcd_lib_update_screen();
}

void lcd_menu_autoStart()
{
    char buffer[64];
    int waited = (millis() - lastStartCheck)/1000;

    if (!card.isOk()) {
        lcd_info_screen(lcd_menu_main);
        lcd_lib_draw_string_centerP(16, PSTR("Reading card..."));
        lcd_lib_update_screen();
        lcd_clear_cache();
        card.initsd();
        return;
    }

    // Prepare for usb-print, wait 5 seconds

    lcd_lib_clear();
    sprintf_P(buffer, PSTR("Wait '%s' %d/5s"), fnAutoPrint, waited);
    lcd_lib_draw_string(1, 20, buffer);
    lcd_lib_update_screen();

    if (waited >= 5) {

        // Check for "autoprint" file in root dir
        card.openFile(fnAutoPrint, true);
        if (card.isFileOpen()) {

            card.closefile();

            lcd_lib_draw_string(1, 30, "got it...");
            lcd_lib_draw_string(1, 40, "start print...");

            lcd_lib_beep();

            //
            // Find filenumber for downloaded file and update cache:
            //
            // cache-id: filenumber
            // cache-type: 0: file, 1: folder
            //
            uint16_t fileCnt = card.getnrfilenames();

            for(uint16_t i=0;i<fileCnt;i++)
            {
                card.getfilename(i);
                // SERIAL_ECHO("update cache, i, filename: ");
                // SERIAL_ECHOLN(i);
                // SERIAL_ECHOLN(" ");
                // SERIAL_ECHOLN(card.filename);
                // XXX card.filename is uppercase!
                if (strcmp(card.filename, fnAutoPrint) == 0) {

                    // Update "Name-Cache"
                    lcd_sd_menu_filename_callback(i+1);
                    lcd_sd_menu_details_callback(i+1);
                    break;
                }
            }

            printSelectedFile(fnAutoPrint);
        }
        else {
            lcd_change_to_menu(lcd_menu_main);
        }

        // Unset autoprint variable to prevent 'print-loop'
        fnAutoPrint[0] = '\0';
    }
}

/* Warning: This function is called from interrupt context */
void lcd_buttons_update()
{
    lcd_lib_buttons_update_interrupt();
}

#endif//ENABLE_ULTILCD2
