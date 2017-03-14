#!/usr/bin/env python
"""
Two way communication program for taking readings from and controlling an ISCO Pump controller.
Uses an external USB to RS485 converter that is connected to the DB25 on the ISCO controller.

Written for python2.7

Company: Interface Fluidics
Written by: Stuart de Haas
Created: March 08, 2017
"""

import serial 
import serial.tools.list_ports
import struct #Used to convert readings to floating point
import time # Used for delays
from time import gmtime, strftime # Used for real time clock
import logging # Used to output data and info to file and console
import thread # Used to take input while outputting data stream
import os.path
import sys

# modbus must be installed manually on the computer. Try 'pip install modbus_tk' or google it
import modbus_tk
import modbus_tk.defines as cst
from modbus_tk import modbus_rtu

# Change the frequency at which readings are taken
SAMPLE_FREQ = 0.5 # Hz

# debug mode allows the program to run without being connected to the pumps.
# Not all functionality can be tested but it can be usefull 
DEBUG_MODE = False

# Keep Track of software version
SOFTWARE_VERSION = 'V1.0; Last Update: 2017-March-10'
INTERRUPT_FLAG = False

# Address used for reading/writing data
#CURRENT_PRESSURE_START_ADDRESS = 72 #Start at the address for Pressure of pump A.
#BYTES_TO_READ = 10 # 5 32bit numbers, volume A remaining is not used
#UNITS_ADDRESS = 84 # Address of registers containing the units being used


def setup():
    """Run initialization of system and connect to controller.
    
    setup() is run once at the beginning of the program to configure the settings
    and connect to the ISCO controller. It creates a 'logger' to output to either 
    both a file and the console or just to the console. It also connects to the ISCO
    and checks if communication is working correctly. Finally, it creates a header
    that contains inital conditions of the pump such as units and max pressure settings.
    """

    print("\n\nHello and welcome to the ISCO Pump communication program!")
    print("Interface Fluidics\n")

    test_date = strftime("%Y%m%d")
    record_format = "%(asctime)s\t%(name)s\t%(levelname)s\t%(message)s"

    while True:
        cmd = raw_input("Would you like to log the data to a file? (y)es or (n)o?\n")
        if cmd == 'y':
            # Loop until a vailid file name is selected
            while True:
                name_of_test = raw_input("Please provide a filename suffix: ")
                # Start a log to keep track of stuff
                log_name = "log_files\\" + test_date + '_' + name_of_test+'.log'
                if os.path.exists(log_name):
                    print(log_name + " already exists. Please try again.\n")
                    continue
                else:
                    break
            print("Your log name will be: "+ log_name + '\n')

            # Create a logger for outputting to a file
            logging.basicConfig(filename=log_name, format=record_format, datefmt='%I:%M:%S %p', level=logging.DEBUG)

            # Then create a second logger to output to the console
            console = logging.StreamHandler()
            console.setLevel(logging.INFO)
            # set a format which is simpler for console use
            formatter = logging.Formatter('%(name)-12s: %(levelname)-8s %(message)s')
            # tell the handler to use this format
            console.setFormatter(formatter)
            # add the handler to the root logger
            logging.getLogger('').addHandler(console)
            break

        elif cmd =='n':
            # If no output file is wanted then output to the console only
            # Set level=logging.DEBUG for more info
            logging.basicConfig(format=record_format, level=logging.INFO)
            break
        else:
            print("Invalid Response")
            continue

        
    # Create the header for the file/console
    logging.debug("Software Version: " + SOFTWARE_VERSION)
    logging.debug("Interface Fluidics Welcomes you!")
    logging.debug("Date and Time: " + strftime("%Y-%m-%d %I:%M %p") )
    

    print("Let's connect to the ISCO Controller...")

    
    # Keep trying to connect to the controller until it works or they exit
    while True:
        # Generate a list of USB ports
        ports = list(serial.tools.list_ports.comports())
        print("Available Ports:")
        for p in ports:
            print(p)

        choice = raw_input("\nWhich port would you like to try? i.e. 'COM6' (or (e)xit)\n")
        if choice == "e":
            sys.exit() # Exits without doing anything else
        else:

            try:
                # In debug mode the connection step is skipped so it works without an ISCO
                if DEBUG_MODE == True:
                    logging.debug("Debug mode enabled")
                    return True

                #Connect to the slave
                master = modbus_rtu.RtuMaster(
                serial.Serial(port=choice, baudrate=19200, bytesize=8, parity=serial.PARITY_EVEN, stopbits=1, xonxoff=0)
                )
                master.set_timeout(5.0)
                master.set_verbose(False) # Set to 'True' for more descriptive output
                on_A, on_B = CheckIfOn(master) # Just to check if it's working
                #logging.info("connected to port " + choice)
                # If the port works, break from loop
                break
            except modbus_tk.exceptions.ModbusInvalidResponseError as exc:
                #Modbus recieved an invalid response. Occurs when nothing is connected
                print("Invalid response from " + choice + ".\n\nPlease try again.")
                continue
            except:
                # If anything else fails during connection, let them try again
                print ("Unexpected error:", sys.exc_info()[0])
                print("\n\nTry Again")
                continue


    ListPumpSettings(master)

    return master # return the ISCO controller serial connection 'object'


def ListPumpSettings(master):
    """ Read from ISCO Controller then output Max Pressures, Max Flowrates and if pumps are on or off"""

    # Need a delay between readings otherwise the ISCO can't keep up
    time.sleep(0.2)
    PRESSURE_UNIT, FLOW_UNIT = ReadUnits(master)
    time.sleep(0.2)
    pressure_A, flowRate_A, pressure_B, flowRate_B = CheckMaxPressureFlow(master)
    time.sleep(0.2)
    on_A, on_B = CheckIfOn(master)
    time.sleep(0.2)

    # Output current ISCO settings to file/header
    logging.info("Pressure Unit: " + PRESSURE_UNIT + "; Flow Rate Unit: " + FLOW_UNIT)
    logging.info("Max Pressure -> Pump A: " + str(pressure_A) + PRESSURE_UNIT + ", Pump B: " + str(pressure_B) + PRESSURE_UNIT)
    logging.info("Max Flow Rate -> Pump A: " + str(flowRate_A) + FLOW_UNIT + ", Pump B: " + str(flowRate_B) + FLOW_UNIT)
    logging.info("Pump A is " + on_A + ", Pump B is " + on_B)

    global INTERRUPT_FLAG
    INTERRUPT_FLAG = False


def ReadUnits(master):
    """Reads the current units from the ISCO controller"""

    # Read from device (device address 1, command, coil address 84, 8 bits to read)
    # Refer to ISCO controller Section on modbus protocol and/or the online resources
    # Outputs a tuple of bits (actually ints I think) that indicate 
    # True/False for the current units
    unit_byte = master.execute(1, cst.READ_COILS, 84, 8)

    # example output: unit_byte = [0, 1, 0, 0, 1, 0, 0, 0]
    # unit_byte[1] == 1 (same as == True) 
    # this means the units are in 'BAR'
    if unit_byte[0]:
        PRESSURE_UNIT = 'ATM'
    elif unit_byte[1]:
        PRESSURE_UNIT = 'BAR'
    elif unit_byte[2]:
        PRESSURE_UNIT = 'kPa'
    elif unit_byte[3]:
        PRESSURE_UNIT = 'PSI'

    if unit_byte[4]:
        FLOW_UNIT = 'ml/min'
    elif unit_byte[5]:
        FLOW_UNIT = 'ml/hr'
    elif unit_byte[6]:
        FLOW_UNIT = 'ul/min'
    elif unit_byte[7]:
        FLOW_UNIT = 'ul/hr'

    return PRESSURE_UNIT, FLOW_UNIT
    
def CheckIfOn(master):
    """ Check the status registers to see which pumps are running """

    pump_status = master.execute(1, cst.READ_COILS, 0, 2)

    if pump_status[0]:
        pumpA = 'on'
    else: 
        pumpA = 'off'

    if pump_status[1]:
        pumpB = 'on'
    else:
        pumpB = 'off'

    return [pumpA, pumpB]

def CheckMaxPressureFlow(master):
    """ Check the maximum pressure and flow rate settings """

    readings = master.execute(1, cst.READ_HOLDING_REGISTERS, 32, 20)

    # holding register readings come as two 16-bit integers that represent 
    # a 32-bit floating point number. They must be converted!
    pressure_A = TupleToFloat(readings[0:2])
    pressure_B = TupleToFloat(readings[2:4])
    flowRate_A = TupleToFloat(readings[16:18])
    flowRate_B = TupleToFloat(readings[18:20])

    return [pressure_A, flowRate_A, pressure_B, flowRate_B]

def TupleToFloat(tup):
    """ Convert two 16bit ints to a 32 bit IEEE 754 floating point """

    # 'a' is first 16-bits and 'b' is the next 16-bits
    a,b = tup[0], tup[1]
    # bit-shift 'a' and concatenate with 'b'
    # i.e. let: a=0b0010, b=0b0110
    # a<<4 == 0b00100000 (move each bit left 4 places)
    # a + b = 0b00100110 (combine a and b, same as addition) 
    num = (a << 16) + b
    # interpret this 32-bit number as a float (not the same as type casting)
    # look it up on Wiki if you don't know how floats work
    output = struct.unpack('f', struct.pack('I', num))[0]
    # Output a floating point number 
    return(output)


def ReadRegisters(master):
    """Read the pressure and flow rate registers for pumps A and B then return as floats"""

    # If we are in debug mode then just output this data for testing purposes
    if DEBUG_MODE == True:
        return [5.67, (-6.3), 7.0, 8.99]

    readings = master.execute(1, cst.READ_HOLDING_REGISTERS, 72, 10)
    pressure_A = TupleToFloat(readings[0:2])
    flowRate_A = TupleToFloat(readings[2:4])
    pressure_B = TupleToFloat(readings[6:8])
    flowRate_B = TupleToFloat(readings[8:10])

    return [pressure_A, flowRate_A, pressure_B, flowRate_B]


def ControlPumps(master):
    """ Allow the user to turn the pumps on or off. """

    while True:
        cmd = raw_input("Pump A on -> onA\nPump A off -> offA\nPump B on -> onB\nPump B off -> offB\nExit -> e\n")
        if cmd == 'onA':
            master.execute(1, cst.WRITE_SINGLE_COIL, 0, output_value=1)
            logging.info("Pump A set to on")
        elif cmd == 'offA':
            master.execute(1, cst.WRITE_SINGLE_COIL, 0, output_value=0)
            logging.info("Pump A set to off")
        elif cmd == 'onB':
            master.execute(1, cst.WRITE_SINGLE_COIL, 1, output_value=1)
            logging.info("Pump B set to on")
        elif cmd == 'offB':
            master.execute(1, cst.WRITE_SINGLE_COIL, 1, output_value=0)
            logging.info("Pump B set to off")
        elif cmd == 'e':
            break
        else:
            print("Please try again\n")

        global INTERRUPT_FLAG
        INTERRUPT_FLAG = False


def logReadings(master, data_logger):
    """Formats the data in a tab seperated format for easy viewing and export to excel"""

    global INTERRUPT_FLAG
    while INTERRUPT_FLAG == False:
        readings = ReadRegisters(master)
        data_logger.info(strftime(str(readings[0]) + '\t' + str(readings[1]) + '\t' + str(readings[2]) + '\t' + str(readings[3])))
        time.sleep(1/SAMPLE_FREQ)

    logging.debug("User Interrupt")
    INTERRUPT_FLAG = False
    return


def userInterrupt():
    """ Function waits for user input while data is being output. 
    
    This function is called and waits at 'raw_input' until the user presses 'enter'.
    Then the flag is set to True which tells the data output thread to stop."""

    # Must use global so it works across multiple threads
    global INTERRUPT_FLAG

    # System waits here while outputting data
    raw_input()
    INTERRUPT_FLAG = True


def main():
    """Main function. Where the magic happens"""

    # Used to stop data output
    global INTERRUPT_FLAG

    # Run the system setup
    master = setup()
    logging.info("Setup Complete")
    
    # Create a logger tag used for all data output so it can be searched for in the output file
    data_logger = logging.getLogger('DATA_OUT') # DATA_OUT is the name of the log 'tag'

    while True:
        print("\nWhat would you like to do?")
        cmd = raw_input("Stream Pressure and Flow Data -> s\nList Pump Settings -> l\nControl Pumps -> c\nExit -> e\n")
        if cmd == 's':
            INTERRUPT_FLAG = False
            # Print a header for the data
            print("\nPress Enter for Menu\n")
            data_logger.info("Pressure A\tFlow Rate A\tPressure B\tFlow Rate B")
            # Create a new thread (parrallel process) that outputs data
            thread.start_new_thread( logReadings, (master, data_logger)) 
        elif cmd == 'l':
            ListPumpSettings(master)
            print("Press Enter")
        elif cmd == 'c':
            ControlPumps(master)
            print("Press Enter")
        elif cmd == 'e':
            logging.info("Now Exiting...")
            return
        else:
            print("Command not recognized. Try again.\n")
            continue

        # Wait here during data output until user triggers the INTERRUPT_FLAG
        userInterrupt()





# This is where the main function is actually called
if __name__ == "__main__":
    main()
