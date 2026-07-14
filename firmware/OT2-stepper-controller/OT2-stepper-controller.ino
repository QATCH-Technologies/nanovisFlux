
#include <Arduino.h>
#include "DualHBridgeStepper.h"

// #define DEBUG

// Motor X: Gantry left/right
#define MOTOR_X_E1 1  // PWM
#define MOTOR_X_E2 2  // PWM
#define MOTOR_X_M1 3
#define MOTOR_X_M2 4

// Motor Y: Gantry front/back
#define MOTOR_Y_E1 5  // PWM
#define MOTOR_Y_E2 6  // PWM
#define MOTOR_Y_M1 7
#define MOTOR_Y_M2 8

// Motor Z: Pipette 1 up/down
#define MOTOR_Z_E1 9   // PWM
#define MOTOR_Z_E2 10  // PWM
#define MOTOR_Z_M1 11
#define MOTOR_Z_M2 12

// Motor A: Pipette 2 up/down
#define MOTOR_A_E1 9   // PWM
#define MOTOR_A_E2 10  // PWM
#define MOTOR_A_M1 11
#define MOTOR_A_M2 12

// Relay: Switch Motors A & Z
#define MOTOR_RELAY_IN4 24
#define MOTOR_RELAY_IN3 25
#define MOTOR_RELAY_IN2 26
#define MOTOR_RELAY_IN1 27

// Motor B: Pipette 1 plunger
#define MOTOR_B_E1 28  // PWM
#define MOTOR_B_E2 29  // PWM
#define MOTOR_B_M1 30
#define MOTOR_B_M2 31

// Motor C: Pipette 2 plunger
#define MOTOR_C_E1 255  // PWM
#define MOTOR_C_E2 255  // PWM
#define MOTOR_C_M1 255
#define MOTOR_C_M2 255

// Touch Probe
#define PROBE_GND 34
#define PROBE_TOUCH 35

// Endstop switches
#define MOTOR_X_SW_IN 14  // active low
#define MOTOR_Y_SW_IN 15  // active low
#define MOTOR_Z_SW_IN 16  // active high
#define MOTOR_A_SW_IN 17  // active high
#define MOTOR_B_SW_IN 18  // active high
#define MOTOR_C_SW_IN 19  // active high

#define PCB_LED 13

// Pin read state when switch is pressed
#define MOTOR_X_SW_HIT LOW
#define MOTOR_Y_SW_HIT LOW
#define MOTOR_Z_SW_HIT HIGH
#define MOTOR_A_SW_HIT HIGH
#define MOTOR_B_SW_HIT HIGH
#define MOTOR_C_SW_HIT HIGH

// Max PWM value for each motor (too big may blow H-Bridge)
#define MOTOR_X_MAX_PWM 666
#define MOTOR_Y_MAX_PWM 666
#define MOTOR_Z_MAX_PWM 725
#define MOTOR_A_MAX_PWM 725
#define MOTOR_B_MAX_PWM 725
#define MOTOR_C_MAX_PWM 725

// reboot is the same for all ARM devices
#define CPU_RESTART_ADDR ((uint32_t *)0xE000ED0C)
#define CPU_RESTART_VAL (0x5FA0004)
#define REBOOT (*CPU_RESTART_ADDR = CPU_RESTART_VAL)

DualHBridgeStepper MOTOR_X(MOTOR_X_M1, MOTOR_X_E1, MOTOR_X_M2, MOTOR_X_E2, MOTOR_X_MAX_PWM);
DualHBridgeStepper MOTOR_Y(MOTOR_Y_M1, MOTOR_Y_E1, MOTOR_Y_M2, MOTOR_Y_E2, MOTOR_Y_MAX_PWM);
DualHBridgeStepper MOTOR_Z(MOTOR_Z_M1, MOTOR_Z_E1, MOTOR_Z_M2, MOTOR_Z_E2, MOTOR_Z_MAX_PWM);
DualHBridgeStepper MOTOR_A(MOTOR_A_M1, MOTOR_A_E1, MOTOR_A_M2, MOTOR_A_E2, MOTOR_A_MAX_PWM);
DualHBridgeStepper MOTOR_B(MOTOR_B_M1, MOTOR_B_E1, MOTOR_B_M2, MOTOR_B_E2, MOTOR_B_MAX_PWM);
DualHBridgeStepper MOTOR_C(MOTOR_C_M1, MOTOR_C_E1, MOTOR_C_M2, MOTOR_C_E2, MOTOR_C_MAX_PWM);

// Specify homing direction, movement must be toward endstop
// false = backwards; true = forwards;
const bool MOTOR_X_HomingDir = true;
const bool MOTOR_Y_HomingDir = true;
const bool MOTOR_Z_HomingDir = true;
const bool MOTOR_A_HomingDir = true;
const bool MOTOR_B_HomingDir = false;
const bool MOTOR_C_HomingDir = false;

// Motor Movement Parameters (X, Y, Z, A, B, C)
const bool MOTOR_DIR_INVERT[6] = { true, true, true, true, false, false };
const long ENDSTOP_LIMITS[6] = { 60000, 52000, 160000, 160000, 20000, 20000 };
long ENDSTOP_BOUNCE[6] = { 1000, 1000, 1500, 1500, 1250, 1250 };
float TRAVEL_ACCELS[6] = { 69000, 69000, 69000, 69000, 3200, 3200 };
float TRAVEL_SPEEDS[6] = { 16000, 16000, 32000, 32000, 6900, 6900 };
float HOMING_ACCELS[6] = { 1E6, 1E6, 1E6, 1E6, 1E6, 1E6 };
float HOMING_SPEEDS[6] = { 8000, 8000, 12000, 12000, 5000, 5000 };
long CUSTOM_LIMITS[6];

bool MOVEMENT_MODE = false;  // false = absolute; true = relative
bool MOVEMENT_SAFE = true;   // unset with M911

bool MOTORS_MOVING = false;
bool MOTORS_HOMED[6] = { false, false, false, false, false, false };

// G38.X flags for touch probe
bool stop_on_probe_high = false;
bool stop_on_probe_low = false;
bool error_on_failure = false;
bool probe_contacted = false;
uint8_t probe_count = 0;

// Function prototypes
void switch_relays(bool motor_en);
bool home_stepper(char motor);

void setup() {
  Serial.begin(115200);

  Serial.println("OpenFlux OT-2 Stepper Controller");
  Serial.println("Version 1.0-alpha (2026-07-10)");
  Serial.println("QATCH Technologies LLC");

  Serial.println("Booting...");

  MOTOR_X.setAcceleration(TRAVEL_ACCELS[0]);
  MOTOR_X.setMaxSpeed(TRAVEL_SPEEDS[0]);
  MOTOR_Y.setAcceleration(TRAVEL_ACCELS[1]);
  MOTOR_Y.setMaxSpeed(TRAVEL_SPEEDS[1]);
  MOTOR_Z.setAcceleration(TRAVEL_ACCELS[2]);
  MOTOR_Z.setMaxSpeed(TRAVEL_SPEEDS[2]);
  MOTOR_A.setAcceleration(TRAVEL_ACCELS[3]);
  MOTOR_A.setMaxSpeed(TRAVEL_SPEEDS[3]);
  MOTOR_B.setAcceleration(TRAVEL_ACCELS[4]);
  MOTOR_B.setMaxSpeed(TRAVEL_SPEEDS[4]);
  MOTOR_C.setAcceleration(TRAVEL_ACCELS[5]);
  MOTOR_C.setMaxSpeed(TRAVEL_SPEEDS[5]);

  CUSTOM_LIMITS[0] = ENDSTOP_LIMITS[0];
  CUSTOM_LIMITS[1] = ENDSTOP_LIMITS[1];
  CUSTOM_LIMITS[2] = ENDSTOP_LIMITS[2];
  CUSTOM_LIMITS[3] = ENDSTOP_LIMITS[3];
  CUSTOM_LIMITS[4] = ENDSTOP_LIMITS[4];
  CUSTOM_LIMITS[5] = ENDSTOP_LIMITS[5];

  pinMode(MOTOR_X_SW_IN, INPUT_PULLUP);
  pinMode(MOTOR_Y_SW_IN, INPUT_PULLUP);
  pinMode(MOTOR_Z_SW_IN, INPUT_PULLUP);
  pinMode(MOTOR_A_SW_IN, INPUT_PULLUP);
  pinMode(MOTOR_B_SW_IN, INPUT_PULLUP);
  pinMode(MOTOR_C_SW_IN, INPUT_PULLUP);

  pinMode(MOTOR_RELAY_IN4, OUTPUT);
  pinMode(MOTOR_RELAY_IN3, OUTPUT);
  pinMode(MOTOR_RELAY_IN2, OUTPUT);
  pinMode(MOTOR_RELAY_IN1, OUTPUT);

  switch_relays(false);  // turn off

  // Touch probe
  pinMode(PROBE_GND, OUTPUT);
  pinMode(PROBE_TOUCH, INPUT_PULLUP);
  digitalWrite(PROBE_GND, LOW);

  Serial.println("ok");
}

void loop() {
  String message_str = "";
  if (Serial.available())
    message_str = Serial.readStringUntil('\n').toUpperCase().trim();

  if (message_str.startsWith("G0") || message_str.startsWith("G1")
      || message_str.startsWith("G38")) {
    uint8_t index;
    String value_str;
    float speed = 0.0;
    float speed_pct = 1.0;  // when XY both move w/ G1 (linear speed)
    bool move_axis[6] = { false, false, false, false, false, false };
    long positions[6] = { 0, 0, 0, 0, 0, 0 };

    // parse flags, if provided in command
    if (message_str.indexOf("X") > 0) move_axis[0] = true;
    if (message_str.indexOf("Y") > 0) move_axis[1] = true;
    if (message_str.indexOf("Z") > 0) move_axis[2] = true;
    if (message_str.indexOf("A") > 0) move_axis[3] = true;
    if (message_str.indexOf("B") > 0) move_axis[4] = true;
    if (message_str.indexOf("C") > 0) move_axis[5] = true;

    index = 0;
    for (uint8_t i = 0; i <= 5; i++) {
      if (move_axis[i] && !MOTORS_HOMED[i]) {
        char motors_by_index[6] = { 'X', 'Y', 'Z', 'A', 'B', 'C' };
        Serial.printf("NOT ok (axis %c not homed)\n", motors_by_index[i]);
        return;  // no movement allowed without homing first
      }
      if (message_str.startsWith("G38")) {
        if (move_axis[i]) {
          if (++index > 1) {
            Serial.println("NOT ok (too many axes)");
            return;  // no movement allowed with more than 1 axis
          }
        }
      }
    }

    // Set flag to reply OK even if no movement required
    MOTORS_MOVING = true;

    // Touch probe commands (G38.X)
    stop_on_probe_high = false;
    stop_on_probe_low = false;
    error_on_failure = false;
    if (message_str.startsWith("G38.2"))
      stop_on_probe_high = error_on_failure = true;
    if (message_str.startsWith("G38.3")) stop_on_probe_high = true;
    if (message_str.startsWith("G38.4"))
      stop_on_probe_low = error_on_failure = true;
    if (message_str.startsWith("G38.5")) stop_on_probe_low = true;

    if (move_axis[0]) {
      index = message_str.indexOf("X") + 1;
      value_str = message_str.substring(index);
      index = value_str.indexOf(" ");
      if (index > 0) value_str = value_str.substring(0, index);
      positions[0] = value_str.toInt();
    }
    if (move_axis[1]) {
      index = message_str.indexOf("Y") + 1;
      value_str = message_str.substring(index);
      index = value_str.indexOf(" ");
      if (index > 0) value_str = value_str.substring(0, index);
      positions[1] = value_str.toInt();
    }
    if (move_axis[2]) {
      index = message_str.indexOf("Z") + 1;
      value_str = message_str.substring(index);
      index = value_str.indexOf(" ");
      if (index > 0) value_str = value_str.substring(0, index);
      positions[2] = value_str.toInt();
    }
    if (move_axis[3]) {
      index = message_str.indexOf("A") + 1;
      value_str = message_str.substring(index);
      index = value_str.indexOf(" ");
      if (index > 0) value_str = value_str.substring(0, index);
      positions[3] = value_str.toInt();
    }
    if (move_axis[4]) {
      index = message_str.indexOf("B") + 1;
      value_str = message_str.substring(index);
      index = value_str.indexOf(" ");
      if (index > 0) value_str = value_str.substring(0, index);
      positions[4] = value_str.toInt();
    }
    if (move_axis[5]) {
      index = message_str.indexOf("C") + 1;
      value_str = message_str.substring(index);
      index = value_str.indexOf(" ");
      if (index > 0) value_str = value_str.substring(0, index);
      positions[5] = value_str.toInt();
    }

    DualHBridgeStepper *stepper = NULL;
    for (uint8_t i = 0; i <= 5; i++) {
      if (move_axis[i]) {
        switch (i) {
          case 0: stepper = &MOTOR_X; break;
          case 1: stepper = &MOTOR_Y; break;
          case 2: stepper = &MOTOR_Z; break;
          case 3: stepper = &MOTOR_A; break;
          case 4: stepper = &MOTOR_B; break;
          case 5: stepper = &MOTOR_C; break;
        }

        speed = TRAVEL_SPEEDS[i];
        speed_pct = 1.0;
        if (message_str.startsWith("G1") || message_str.startsWith("G38")) {
          index = message_str.indexOf("F") + 1;
          if (index > 0) {
            value_str = message_str.substring(index);
            index = value_str.indexOf(" ");
            if (index > 0) value_str = value_str.substring(0, index);
            speed = value_str.toFloat();
          }
          // Enforce linear movement of X and Y with G1 command
          if (i <= 1 && move_axis[0] && move_axis[1]) {
#ifdef DEBUG
            Serial.printf("Calculating linear motion on axis %i\n", i);
#endif
            // X and Y axes only, both are moving
            float delta_x, delta_y;
            if (MOVEMENT_MODE) {
              // relative
              delta_x = abs(positions[0]);
              delta_y = abs(positions[1]);
            } else {
              // absolute
              delta_x = abs(MOTOR_X.currentPosition() - positions[0]);
              delta_y = abs(MOTOR_Y.currentPosition() - positions[1]);
            }
            if (i == 0 && delta_x < delta_y)
              speed_pct = ((float)delta_x) / delta_y;
            if (i == 1 && delta_y < delta_x)
              speed_pct = ((float)delta_y) / delta_x;
#ifdef DEBUG
            Serial.printf("Max speed for axis %i: %f\n", i, speed * speed_pct);
#endif
          }
        }

        stepper->setAcceleration(TRAVEL_ACCELS[i]);
        stepper->setMaxSpeed(speed * speed_pct);

        stepper->enableOutputs();
        if (MOVEMENT_MODE) {
          // relative
          stepper->move(MOTOR_DIR_INVERT[i] ? -positions[i] : positions[i]);
        } else {
          // absolute
          stepper->moveTo(MOTOR_DIR_INVERT[i] ? -positions[i] : positions[i]);
        }

        if (MOVEMENT_SAFE) {
          if (!MOTOR_DIR_INVERT[i]) {
            // Valid motor positions from 0 to CUSTOM_LIMITS (positive)
            if (stepper->targetPosition() < 0) stepper->moveTo(0);
            if (stepper->targetPosition() > CUSTOM_LIMITS[i]) {
              stepper->moveTo(CUSTOM_LIMITS[i]);
            }
          } else {
            // Valid motor positions from 0 to -CUSTOM_LIMITS (negative)
            if (stepper->targetPosition() > 0) stepper->moveTo(0);
            if (stepper->targetPosition() < -CUSTOM_LIMITS[i]) {
              stepper->moveTo(-CUSTOM_LIMITS[i]);
            }
          }
        }
      }
    }
  }

  if (message_str.startsWith("G28")) {
    bool home_X = false;
    bool home_Y = false;
    bool home_Z = false;
    bool home_A = false;
    bool home_B = false;
    bool home_C = false;

    // default, if no flags provided in command
    if (message_str.endsWith("G28")) {
      home_X = true;
      home_Y = true;
      home_Z = true;
      home_A = true;
      home_B = true;
      // home_C = true;  // does not exist
    }

    // parse flags, if provided in command
    if (message_str.indexOf("X") > 0) home_X = true;
    if (message_str.indexOf("Y") > 0) home_Y = true;
    if (message_str.indexOf("Z") > 0) home_Z = true;
    if (message_str.indexOf("A") > 0) home_A = true;
    if (message_str.indexOf("B") > 0) home_B = true;
    if (message_str.indexOf("C") > 0) home_C = true;

    String homing_motors = "";
    homing_motors.reserve(13);
    if (home_A) homing_motors += " A";
    if (home_Z) homing_motors += " Z";
    if (home_X) homing_motors += " X";
    if (home_Y) homing_motors += " Y";
    if (home_B) homing_motors += " B";
    if (home_C) homing_motors += " C";
    Serial.printf("Homing%s...\n", homing_motors.c_str());

    // Homing order: A, Z, Y, X, B, C
    // Do not change this order without careful thought
    if (home_A && !home_stepper('A')) return;
    if (home_Z && !home_stepper('Z')) return;
    if (home_X && !home_stepper('X')) return;
    if (home_Y && !home_stepper('Y')) return;
    if (home_B && !home_stepper('B')) return;
    if (home_C && !home_stepper('C')) return;

    // Main loop sends "ok" when all motors stop moving (not here)
    // Serial.println("ok");
  }

  if (message_str.startsWith("G38")) {
    // Touch Probe

    // TODO: Not implemented
  }

  if (message_str.startsWith("G90")) {
    MOVEMENT_MODE = false;  // absolute
    Serial.println("Absolute mode set.");
    Serial.println("ok");
  }

  if (message_str.startsWith("G91")) {
    MOVEMENT_MODE = true;  // relative
    Serial.println("Relative mode set.");
    Serial.println("ok");
  }

  if (message_str.startsWith("M30")) {
    // RESET
    Serial.println("Resetting...");
    REBOOT;  // does not return
  }

  if (message_str.startsWith("M112")) {
    // M112 - Emergency stop
    // stop ALL movement without decel
    MOTOR_X.setCurrentPosition(0);
    MOTOR_Y.setCurrentPosition(0);
    MOTOR_Z.setCurrentPosition(0);
    MOTOR_A.setCurrentPosition(0);
    MOTOR_B.setCurrentPosition(0);
    MOTOR_C.setCurrentPosition(0);
    // disable ALL output pins
    MOTOR_X.disableOutputs();
    MOTOR_Y.disableOutputs();
    MOTOR_Z.disableOutputs();
    MOTOR_A.disableOutputs();
    MOTOR_B.disableOutputs();
    MOTOR_C.disableOutputs();
    // mark ALL motors as requiring re-homing
    MOTORS_HOMED[0] = false;
    MOTORS_HOMED[1] = false;
    MOTORS_HOMED[2] = false;
    MOTORS_HOMED[3] = false;
    MOTORS_HOMED[4] = false;
    MOTORS_HOMED[5] = false;
  }

  if (message_str.startsWith("M114")) {
    Serial.print(" X:");
    Serial.print(MOTORS_HOMED[0] ? abs(MOTOR_X.currentPosition()) : -1);
    Serial.print(" Y:");
    Serial.print(MOTORS_HOMED[1] ? abs(MOTOR_Y.currentPosition()) : -1);
    Serial.print(" Z:");
    Serial.print(MOTORS_HOMED[2] ? abs(MOTOR_Z.currentPosition()) : -1);
    Serial.print(" A:");
    Serial.print(MOTORS_HOMED[3] ? abs(MOTOR_A.currentPosition()) : -1);
    Serial.print(" B:");
    Serial.print(MOTORS_HOMED[4] ? abs(MOTOR_B.currentPosition()) : -1);
    Serial.print(" C:");
    Serial.print(MOTORS_HOMED[5] ? abs(MOTOR_C.currentPosition()) : -1);
    Serial.println();
    Serial.println("ok");
  }

  if (message_str.startsWith("M201")) {
    // Set hard limits in CUSTOM_LIMITS array
    // NOTE: If MOVEMENT_SAFE, restrict to range
    //       0 <= limit <= ENDSTOP_LIMITS[i]

    uint8_t index;
    String value_str;
    bool set_axis[6] = { false, false, false, false, false, false };
    long custom_limits[6] = { 0, 0, 0, 0, 0, 0 };

    // parse flags, if provided in command
    if (message_str.indexOf("X") > 0) set_axis[0] = true;
    if (message_str.indexOf("Y") > 0) set_axis[1] = true;
    if (message_str.indexOf("Z") > 0) set_axis[2] = true;
    if (message_str.indexOf("A") > 0) set_axis[3] = true;
    if (message_str.indexOf("B") > 0) set_axis[4] = true;
    if (message_str.indexOf("C") > 0) set_axis[5] = true;

    if (set_axis[0]) {
      index = message_str.indexOf("X") + 1;
      value_str = message_str.substring(index);
      index = value_str.indexOf(" ");
      if (index > 0) value_str = value_str.substring(0, index);
      custom_limits[0] = value_str.toInt();
    }
    if (set_axis[1]) {
      index = message_str.indexOf("Y") + 1;
      value_str = message_str.substring(index);
      index = value_str.indexOf(" ");
      if (index > 0) value_str = value_str.substring(0, index);
      custom_limits[1] = value_str.toInt();
    }
    if (set_axis[2]) {
      index = message_str.indexOf("Z") + 1;
      value_str = message_str.substring(index);
      index = value_str.indexOf(" ");
      if (index > 0) value_str = value_str.substring(0, index);
      custom_limits[2] = value_str.toInt();
    }
    if (set_axis[3]) {
      index = message_str.indexOf("A") + 1;
      value_str = message_str.substring(index);
      index = value_str.indexOf(" ");
      if (index > 0) value_str = value_str.substring(0, index);
      custom_limits[3] = value_str.toInt();
    }
    if (set_axis[4]) {
      index = message_str.indexOf("B") + 1;
      value_str = message_str.substring(index);
      index = value_str.indexOf(" ");
      if (index > 0) value_str = value_str.substring(0, index);
      custom_limits[4] = value_str.toInt();
    }
    if (set_axis[5]) {
      index = message_str.indexOf("C") + 1;
      value_str = message_str.substring(index);
      index = value_str.indexOf(" ");
      if (index > 0) value_str = value_str.substring(0, index);
      custom_limits[5] = value_str.toInt();
    }

    for (uint8_t i = 0; i <= 5; i++) {
      if (set_axis[i])
        if (custom_limits[i] >= 0)
          if (custom_limits[i] <= ENDSTOP_LIMITS[i])
            CUSTOM_LIMITS[i] = custom_limits[i];
    }
  }

  if (message_str.startsWith("M204")) {
    // Set accelerations in TRAVEL_ACCELS

    uint8_t index;
    String value_str;
    bool set_axis[6] = { false, false, false, false, false, false };
    float accelerations[6] = { 0, 0, 0, 0, 0, 0 };

    // parse flags, if provided in command
    if (message_str.indexOf("X") > 0) set_axis[0] = true;
    if (message_str.indexOf("Y") > 0) set_axis[1] = true;
    if (message_str.indexOf("Z") > 0) set_axis[2] = true;
    if (message_str.indexOf("A") > 0) set_axis[3] = true;
    if (message_str.indexOf("B") > 0) set_axis[4] = true;
    if (message_str.indexOf("C") > 0) set_axis[5] = true;

    if (set_axis[0]) {
      index = message_str.indexOf("X") + 1;
      value_str = message_str.substring(index);
      index = value_str.indexOf(" ");
      if (index > 0) value_str = value_str.substring(0, index);
      accelerations[0] = value_str.toFloat();
    }
    if (set_axis[1]) {
      index = message_str.indexOf("Y") + 1;
      value_str = message_str.substring(index);
      index = value_str.indexOf(" ");
      if (index > 0) value_str = value_str.substring(0, index);
      accelerations[1] = value_str.toFloat();
    }
    if (set_axis[2]) {
      index = message_str.indexOf("Z") + 1;
      value_str = message_str.substring(index);
      index = value_str.indexOf(" ");
      if (index > 0) value_str = value_str.substring(0, index);
      accelerations[2] = value_str.toFloat();
    }
    if (set_axis[3]) {
      index = message_str.indexOf("A") + 1;
      value_str = message_str.substring(index);
      index = value_str.indexOf(" ");
      if (index > 0) value_str = value_str.substring(0, index);
      accelerations[3] = value_str.toFloat();
    }
    if (set_axis[4]) {
      index = message_str.indexOf("B") + 1;
      value_str = message_str.substring(index);
      index = value_str.indexOf(" ");
      if (index > 0) value_str = value_str.substring(0, index);
      accelerations[4] = value_str.toFloat();
    }
    if (set_axis[5]) {
      index = message_str.indexOf("C") + 1;
      value_str = message_str.substring(index);
      index = value_str.indexOf(" ");
      if (index > 0) value_str = value_str.substring(0, index);
      accelerations[5] = value_str.toFloat();
    }

    // It is safe to pass-thru any value to the stepper driver
    // as it will reject or transform any unreasonable inputs.
    for (uint8_t i = 0; i <= 5; i++)
      if (set_axis[i]) TRAVEL_ACCELS[i] = accelerations[i];
  }

  if (message_str.startsWith("M210")) {
    // Set homing speeds in HOMING_SPEEDS

    uint8_t index;
    String value_str;
    bool set_axis[6] = { false, false, false, false, false, false };
    float homing_speeds[6] = { 0, 0, 0, 0, 0, 0 };

    // parse flags, if provided in command
    if (message_str.indexOf("X") > 0) set_axis[0] = true;
    if (message_str.indexOf("Y") > 0) set_axis[1] = true;
    if (message_str.indexOf("Z") > 0) set_axis[2] = true;
    if (message_str.indexOf("A") > 0) set_axis[3] = true;
    if (message_str.indexOf("B") > 0) set_axis[4] = true;
    if (message_str.indexOf("C") > 0) set_axis[5] = true;

    if (set_axis[0]) {
      index = message_str.indexOf("X") + 1;
      value_str = message_str.substring(index);
      index = value_str.indexOf(" ");
      if (index > 0) value_str = value_str.substring(0, index);
      homing_speeds[0] = value_str.toFloat();
    }
    if (set_axis[1]) {
      index = message_str.indexOf("Y") + 1;
      value_str = message_str.substring(index);
      index = value_str.indexOf(" ");
      if (index > 0) value_str = value_str.substring(0, index);
      homing_speeds[1] = value_str.toFloat();
    }
    if (set_axis[2]) {
      index = message_str.indexOf("Z") + 1;
      value_str = message_str.substring(index);
      index = value_str.indexOf(" ");
      if (index > 0) value_str = value_str.substring(0, index);
      homing_speeds[2] = value_str.toFloat();
    }
    if (set_axis[3]) {
      index = message_str.indexOf("A") + 1;
      value_str = message_str.substring(index);
      index = value_str.indexOf(" ");
      if (index > 0) value_str = value_str.substring(0, index);
      homing_speeds[3] = value_str.toFloat();
    }
    if (set_axis[4]) {
      index = message_str.indexOf("B") + 1;
      value_str = message_str.substring(index);
      index = value_str.indexOf(" ");
      if (index > 0) value_str = value_str.substring(0, index);
      homing_speeds[4] = value_str.toFloat();
    }
    if (set_axis[5]) {
      index = message_str.indexOf("C") + 1;
      value_str = message_str.substring(index);
      index = value_str.indexOf(" ");
      if (index > 0) value_str = value_str.substring(0, index);
      homing_speeds[5] = value_str.toFloat();
    }

    // It is safe to pass-thru any value to the stepper driver
    // as it will reject or transform any unreasonable inputs.
    for (uint8_t i = 0; i <= 5; i++)
      if (set_axis[i]) HOMING_SPEEDS[i] = homing_speeds[i];
  }

  if (message_str.startsWith("M220")) {
    // Set travel speeds in TRAVEL_SPEEDS

    uint8_t index;
    String value_str;
    bool set_axis[6] = { false, false, false, false, false, false };
    float travel_speeds[6] = { 0, 0, 0, 0, 0, 0 };

    // parse flags, if provided in command
    if (message_str.indexOf("X") > 0) set_axis[0] = true;
    if (message_str.indexOf("Y") > 0) set_axis[1] = true;
    if (message_str.indexOf("Z") > 0) set_axis[2] = true;
    if (message_str.indexOf("A") > 0) set_axis[3] = true;
    if (message_str.indexOf("B") > 0) set_axis[4] = true;
    if (message_str.indexOf("C") > 0) set_axis[5] = true;

    if (set_axis[0]) {
      index = message_str.indexOf("X") + 1;
      value_str = message_str.substring(index);
      index = value_str.indexOf(" ");
      if (index > 0) value_str = value_str.substring(0, index);
      travel_speeds[0] = value_str.toFloat();
    }
    if (set_axis[1]) {
      index = message_str.indexOf("Y") + 1;
      value_str = message_str.substring(index);
      index = value_str.indexOf(" ");
      if (index > 0) value_str = value_str.substring(0, index);
      travel_speeds[1] = value_str.toFloat();
    }
    if (set_axis[2]) {
      index = message_str.indexOf("Z") + 1;
      value_str = message_str.substring(index);
      index = value_str.indexOf(" ");
      if (index > 0) value_str = value_str.substring(0, index);
      travel_speeds[2] = value_str.toFloat();
    }
    if (set_axis[3]) {
      index = message_str.indexOf("A") + 1;
      value_str = message_str.substring(index);
      index = value_str.indexOf(" ");
      if (index > 0) value_str = value_str.substring(0, index);
      travel_speeds[3] = value_str.toFloat();
    }
    if (set_axis[4]) {
      index = message_str.indexOf("B") + 1;
      value_str = message_str.substring(index);
      index = value_str.indexOf(" ");
      if (index > 0) value_str = value_str.substring(0, index);
      travel_speeds[4] = value_str.toFloat();
    }
    if (set_axis[5]) {
      index = message_str.indexOf("C") + 1;
      value_str = message_str.substring(index);
      index = value_str.indexOf(" ");
      if (index > 0) value_str = value_str.substring(0, index);
      travel_speeds[5] = value_str.toFloat();
    }

    // It is safe to pass-thru any value to the stepper driver
    // as it will reject or transform any unreasonable inputs.
    for (uint8_t i = 0; i <= 5; i++)
      if (set_axis[i]) TRAVEL_SPEEDS[i] = travel_speeds[i];
  }

  if (message_str.startsWith("M410")) {
    // M410 - Quick stop
    // Stop as quickly as possible, at current pos, with decel
    // No re-homing required.

    // Call stop() on all motors (no-op if axis is not moving)
    MOTOR_X.stop();
    MOTOR_Y.stop();
    MOTOR_Z.stop();
    MOTOR_A.stop();
    MOTOR_B.stop();
    MOTOR_C.stop();
  }

  if (message_str.startsWith("M411")) {
    // Query debug info
    if (message_str.indexOf("READ") == 5) {
      uint8_t index = message_str.lastIndexOf(' ');
      uint8_t pin = message_str.substring(index + 1).toInt();
      if (pin > 0 && pin < 42) {
        bool pin_state = digitalRead(pin);
        Serial.printf("PIN %u = ", pin);
        Serial.println(pin_state ? "HIGH." : "LOW.");
        Serial.println("ok");
      } else {
        Serial.println("Invalid pin.\nok");
      }
    } else {
      Serial.println("Unknown sub-command.\nok");
    }
  }

  if (message_str.startsWith("M421")) {
    // Adjust retraction distance during homing in ENDSTOP_BOUNCE

    uint8_t index;
    String value_str;
    bool set_axis[6] = { false, false, false, false, false, false };
    long debounce[6] = { 0, 0, 0, 0, 0, 0 };

    // parse flags, if provided in command
    if (message_str.indexOf("X") > 0) set_axis[0] = true;
    if (message_str.indexOf("Y") > 0) set_axis[1] = true;
    if (message_str.indexOf("Z") > 0) set_axis[2] = true;
    if (message_str.indexOf("A") > 0) set_axis[3] = true;
    if (message_str.indexOf("B") > 0) set_axis[4] = true;
    if (message_str.indexOf("C") > 0) set_axis[5] = true;

    if (set_axis[0]) {
      index = message_str.indexOf("X") + 1;
      value_str = message_str.substring(index);
      index = value_str.indexOf(" ");
      if (index > 0) value_str = value_str.substring(0, index);
      debounce[0] = value_str.toInt();
    }
    if (set_axis[1]) {
      index = message_str.indexOf("Y") + 1;
      value_str = message_str.substring(index);
      index = value_str.indexOf(" ");
      if (index > 0) value_str = value_str.substring(0, index);
      debounce[1] = value_str.toInt();
    }
    if (set_axis[2]) {
      index = message_str.indexOf("Z") + 1;
      value_str = message_str.substring(index);
      index = value_str.indexOf(" ");
      if (index > 0) value_str = value_str.substring(0, index);
      debounce[2] = value_str.toInt();
    }
    if (set_axis[3]) {
      index = message_str.indexOf("A") + 1;
      value_str = message_str.substring(index);
      index = value_str.indexOf(" ");
      if (index > 0) value_str = value_str.substring(0, index);
      debounce[3] = value_str.toInt();
    }
    if (set_axis[4]) {
      index = message_str.indexOf("B") + 1;
      value_str = message_str.substring(index);
      index = value_str.indexOf(" ");
      if (index > 0) value_str = value_str.substring(0, index);
      debounce[4] = value_str.toInt();
    }
    if (set_axis[5]) {
      index = message_str.indexOf("C") + 1;
      value_str = message_str.substring(index);
      index = value_str.indexOf(" ");
      if (index > 0) value_str = value_str.substring(0, index);
      debounce[5] = value_str.toInt();
    }

    // It is safe to pass-thru any value to the stepper driver
    // as it will reject or transform any unreasonable inputs.
    for (uint8_t i = 0; i <= 5; i++)
      if (set_axis[i]) ENDSTOP_BOUNCE[i] = debounce[i];
  }

  if (message_str.startsWith("M911")) {
    // Toggle movement safety guards
    MOVEMENT_SAFE = !MOVEMENT_SAFE;
    Serial.print("Movement safety guards ");
    if (MOVEMENT_SAFE) Serial.println("ON.");
    else Serial.println("OFF.");
    Serial.println("ok");
  }

  // True means there is active touch on probe
  bool probe_state = digitalRead(PROBE_TOUCH);
  digitalWrite(PCB_LED, probe_state);
  if ((stop_on_probe_high && probe_state) || (stop_on_probe_low && !probe_state)) {
    if (probe_count < 255) probe_count++;
  } else probe_count = 0;

  if (stop_on_probe_high && probe_count > 3) {
    probe_contacted = true;
    MOTOR_X.stop();
    MOTOR_Y.stop();
    MOTOR_Z.stop();
    MOTOR_A.stop();
    MOTOR_B.stop();
    MOTOR_C.stop();
  }
  if (stop_on_probe_low && probe_count > 3) {
    probe_contacted = true;
    MOTOR_X.stop();
    MOTOR_Y.stop();
    MOTOR_Z.stop();
    MOTOR_A.stop();
    MOTOR_B.stop();
    MOTOR_C.stop();
  }

  bool motors_moving = false;

  if (MOTOR_X.isRunning() || MOTOR_Y.isRunning()) {
    // move X and Y axes at the same time (if either is running)
    if (MOTOR_X.isRunning()) motors_moving ^= MOTOR_X.run();
    if (!MOTOR_X.isRunning()) MOTOR_X.disableOutputs();
    if (MOTOR_Y.isRunning()) motors_moving ^= MOTOR_Y.run();
    if (!MOTOR_Y.isRunning()) MOTOR_Y.disableOutputs();
  } else if (MOTOR_Z.isRunning()) {
    // only move Z axis after X and Y are finished moving
    if (MOTOR_Z.isRunning()) motors_moving ^= MOTOR_Z.run();
    if (!MOTOR_Z.isRunning()) MOTOR_Z.disableOutputs();
  } else if (MOTOR_A.isRunning()) {
    // only move A after X, Y and Z are finished moving
    if (MOTOR_A.isRunning()) {
      switch_relays(true);  // select A
      motors_moving ^= MOTOR_A.run();
    }
    if (!MOTOR_A.isRunning()) {
      switch_relays(false);  // turn off
      MOTOR_A.disableOutputs();
    }
  } else if (MOTOR_B.isRunning()) {
    // only move B after X, Y, Z and A are finished moving
    if (MOTOR_B.isRunning()) motors_moving ^= MOTOR_B.run();
    if (!MOTOR_B.isRunning()) MOTOR_B.disableOutputs();
  } else if (MOTOR_C.isRunning()) {
    // only move C after all other motors have finished moving
    if (MOTOR_C.isRunning()) motors_moving ^= MOTOR_C.run();
    if (!MOTOR_C.isRunning()) MOTOR_C.disableOutputs();
  }

  if (MOTORS_MOVING) {
    // Wait to say "ok" until all movements done

    if (!motors_moving) {
      if (!MOTOR_X.isRunning()) MOTOR_X.disableOutputs();
      if (!MOTOR_Y.isRunning()) MOTOR_Y.disableOutputs();
      if (!MOTOR_Z.isRunning()) MOTOR_Z.disableOutputs();
      if (!MOTOR_A.isRunning()) MOTOR_A.disableOutputs();
      if (!MOTOR_B.isRunning()) MOTOR_B.disableOutputs();
      if (!MOTOR_C.isRunning()) MOTOR_C.disableOutputs();

      if (stop_on_probe_high || stop_on_probe_low) {
        Serial.print("[PRB:");
        Serial.print(MOTORS_HOMED[0] ? abs(MOTOR_X.currentPosition()) : -1);
        Serial.print(",");
        Serial.print(MOTORS_HOMED[1] ? abs(MOTOR_Y.currentPosition()) : -1);
        Serial.print(",");
        Serial.print(MOTORS_HOMED[3] ? abs(MOTOR_A.currentPosition()) : -1);
        Serial.println(probe_contacted ? ":1]" : ":0]");
      }

      if (error_on_failure && !probe_contacted) Serial.print("NOT ");
      Serial.println("ok");

      stop_on_probe_high = false;
      stop_on_probe_low = false;
      error_on_failure = false;
      probe_contacted = false;
    }
  }
  MOTORS_MOVING = motors_moving;
}

void switch_relays(bool motor_en) {
  bool pin_state = motor_en ? LOW : HIGH;
  if (digitalReadFast(MOTOR_RELAY_IN1) != pin_state) {
    digitalWrite(MOTOR_RELAY_IN4, pin_state);
    digitalWrite(MOTOR_RELAY_IN3, pin_state);
    digitalWrite(MOTOR_RELAY_IN2, pin_state);
    digitalWrite(MOTOR_RELAY_IN1, pin_state);
  }
}

bool home_stepper(char motor) {
  DualHBridgeStepper *stepper = NULL;
  uint8_t endstop = 0;  // not set
  bool dir = false;
  bool hit = false;
  uint8_t index = 0;

  if (motor == 'X') {
    stepper = &MOTOR_X;
    endstop = MOTOR_X_SW_IN;
    dir = MOTOR_X_HomingDir;
    hit = MOTOR_X_SW_HIT;
    index = 0;
  }
  if (motor == 'Y') {
    stepper = &MOTOR_Y;
    endstop = MOTOR_Y_SW_IN;
    dir = MOTOR_Y_HomingDir;
    hit = MOTOR_Y_SW_HIT;
    index = 1;
  }
  if (motor == 'Z') {
    stepper = &MOTOR_Z;
    endstop = MOTOR_Z_SW_IN;
    dir = MOTOR_Z_HomingDir;
    hit = MOTOR_Z_SW_HIT;
    index = 2;
  }
  if (motor == 'A') {
    stepper = &MOTOR_A;
    endstop = MOTOR_A_SW_IN;
    dir = MOTOR_A_HomingDir;
    hit = MOTOR_A_SW_HIT;
    index = 3;
  }
  if (motor == 'B') {
    stepper = &MOTOR_B;
    endstop = MOTOR_B_SW_IN;
    dir = MOTOR_B_HomingDir;
    hit = MOTOR_B_SW_HIT;
    index = 4;
  }
  if (motor == 'C') {
    stepper = &MOTOR_C;
    endstop = MOTOR_C_SW_IN;
    dir = MOTOR_C_HomingDir;
    hit = MOTOR_C_SW_HIT;
    index = 5;
  }
  if (!stepper || !endstop) {
    Serial.println("NOT ok (null pointer)");
    return false;
  }

  long limit = CUSTOM_LIMITS[index];
  long retro = ENDSTOP_BOUNCE[index];
  float accel = HOMING_ACCELS[index];
  float speed = HOMING_SPEEDS[index];

#ifdef DEBUG
  Serial.printf("limit = %i\n", limit);
  Serial.printf("retro = %i\n", retro);
  Serial.printf("accel = %f\n", accel);
  Serial.printf("speed = %f\n", speed);
#endif

  // Only turn on relays if Motor A
  switch_relays((bool)(motor == 'A'));

  // Move stepper towards endstop (faster)
  stepper->enableOutputs();
  stepper->setMaxSpeed(speed);
  stepper->move(dir ? limit : -limit);

  // Set flag here to disable all motors in main loop later
  // (as a safety precaution, on failure)
  MOTORS_MOVING = true;

  // Listen for initial endstop hit (with debounce)
  uint8_t endstop_hits = 0;
  while (stepper->isRunning() && !Serial.available()) {
    if (digitalRead(endstop) == hit) endstop_hits++;
    else endstop_hits = 0;
    if (endstop_hits >= 3) break;
    stepper->run();
  }

  // Check for error conditions when hitting endstop
  if (stepper->isRunning()) {
    if (Serial.available()) {
      Serial.println("NOT ok (serial pending)");
      stepper->stop();  // Abort movement
      MOTORS_HOMED[index] = false;
      return false;  // Don't move to position without valid home
    }
  } else {
    Serial.println("NOT ok (no endstop found)");
    MOTORS_HOMED[index] = false;
    return false;  // Don't move to position without valid home
  }

  // Move off endstop by a fixed distance
  stepper->setAcceleration(accel);
  stepper->setMaxSpeed(speed / 5);        // 20% initial speed
  stepper->move((dir ? -retro : retro));  // the other way
  stepper->runToPosition();               // BLOCKING

  // Move stepper towards endstop (slower)
  stepper->setMaxSpeed(speed / 10);  // 10% initial speed
  stepper->move((dir ? retro * 2 : -retro * 2));

  // Listen for precise endstop hit (with debounce)
  endstop_hits = 0;
  while (stepper->isRunning() && !Serial.available()) {
    if (digitalRead(endstop) == hit) endstop_hits++;
    else endstop_hits = 0;
    if (endstop_hits >= 3) break;
    stepper->run();
  }

  // Check for error conditions when hitting endstop
  if (stepper->isRunning()) {
    if (Serial.available()) {
      Serial.println("NOT ok (serial pending)");
      stepper->stop();  // Abort movement
      MOTORS_HOMED[index] = false;
      return false;  // Don't move to position without valid home
    }
  } else {
    Serial.println("NOT ok (no endstop found)");
    MOTORS_HOMED[index] = false;
    return false;  // Don't move to position without valid home
  }

  // Set this precise postion as this motor's HOME
  Serial.printf("Homed %c.\n", motor);
  stepper->setCurrentPosition(0);  // also stops movement

  // Turn relays off
  switch_relays(false);

  // Release motor pins
  stepper->disableOutputs();

  MOTORS_HOMED[index] = true;
  return true;
}