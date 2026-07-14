#ifndef DUAL_H_BRIDGE_STEPPER_H
#define DUAL_H_BRIDGE_STEPPER_H

#include <Arduino.h>
#include <AccelStepper.h>

// #define DEBUG

class DualHBridgeStepper : public AccelStepper {
public:
  DualHBridgeStepper(
    uint8_t dir1, uint8_t pwm1, uint8_t dir2, uint8_t pwm2, uint16_t pwmMaxValue = 255)
    : AccelStepper(FULL4WIRE, dir1, pwm1, dir2, pwm2, true), _dir1(dir1),
      _pwm1(pwm1), _dir2(dir2), _pwm2(pwm2), _pwmMaxValue(pwmMaxValue) {
    pinMode(_dir1, OUTPUT);
    pinMode(_pwm1, OUTPUT);
    pinMode(_dir2, OUTPUT);
    pinMode(_pwm2, OUTPUT);

    // Set analog frequency and step count
    _frequency = 25000;  // ultrasonic, 25kHz
    _steps = 32 * 4;     // 128 microsteps per period

    // In case not using microstepping
    _pwm1_value = _pwmMaxValue;
    _pwm2_value = _pwmMaxValue;

    // Set the PWM frequency to ultrasonic
    analogWriteFrequency(_pwm1, _frequency);
    analogWriteFrequency(_pwm2, _frequency);

    // Set ADC resolution to 10-bits (0 to 1023)
    analogWriteResolution(10);
  }

  void setPwmMaxValue(uint8_t pwmMaxValue) {
    _pwmMaxValue = pwmMaxValue;
    _pwm1_value = _pwmMaxValue;
    _pwm2_value = _pwmMaxValue;
  }

protected:
  void step(long step) override {
    if (_steps <= HALF4WIRE) {
      // Explicit "super" call
      AccelStepper::step(step);

    } else {
      microstep(step);  // steps per quadrant
    }
  }

  void microstep(long step) {
    int8_t totalstep = step % _steps;
    if (totalstep < 0) totalstep = _steps + totalstep;

    const uint8_t _perquad = _steps / 4;

    // Convert 0-128 to 0-32 microsteps per quadrant
    uint8_t quadrant = totalstep / _perquad;
    uint8_t microstep = totalstep % _perquad;

    // Skip unused steps for 16 microstepping
    if (_perquad == 16) microstep *= 2;

    // Set PWM values for coil A and coil B
    // before setting the output pin states
    switch (quadrant) {
      case 0:  // 1010
        // Quadrant 1: Steps 0 to 31
        // Coil A: Ramps down (backward)
        // Coil B: Ramps up (backward)
        _pwm1_value = (uint16_t)(_lookupTable[32 - microstep] * _pwmMaxValue);
        _pwm2_value = (uint16_t)(_lookupTable[microstep] * _pwmMaxValue);
        setOutputPins(0b0101);
        break;

      case 1:  // 0110
        // Quadrant 2: Steps 32 to 63
        // Coil A: Ramps up (forward)
        // Coil B: Ramps down (backward)
        _pwm1_value = (uint16_t)(_lookupTable[microstep] * _pwmMaxValue);
        _pwm2_value = (uint16_t)(_lookupTable[32 - microstep] * _pwmMaxValue);
        setOutputPins(0b0110);
        break;

      case 2:  // 0101
        // Quadrant 3: Steps 64 to 95
        // Coil A: Ramps down (forward)
        // Coil B: Ramps up (forward)
        _pwm1_value = (uint16_t)(_lookupTable[32 - microstep] * _pwmMaxValue);
        _pwm2_value = (uint16_t)(_lookupTable[microstep] * _pwmMaxValue);
        setOutputPins(0b1010);
        break;

      case 3:  // 1001
        // Quadrant 4: Steps 96 to 127
        // Coil A: Ramps up (backward)
        // Coil B: Ramps down (forward)
        _pwm1_value = (uint16_t)(_lookupTable[microstep] * _pwmMaxValue);
        _pwm2_value = (uint16_t)(_lookupTable[32 - microstep] * _pwmMaxValue);
        setOutputPins(0b1001);
        break;
    }

#ifdef DEBUG
    Serial.print("step = ");
    Serial.print(step);
    Serial.print("; ");
    Serial.print("totalstep = ");
    Serial.print(totalstep);
    Serial.print("; ");
    Serial.print("_perquad = ");
    Serial.print(_perquad);
    Serial.print("; ");
    Serial.print("quadrant = ");
    Serial.print(quadrant);
    Serial.print("; ");
    Serial.print("microstep = ");
    Serial.print(microstep);
    Serial.print("; ");
    Serial.print("_pwm1_value = ");
    Serial.print(_pwm1_value);
    Serial.print("; ");
    Serial.print("_pwm2_value = ");
    Serial.print(_pwm2_value);
    Serial.print("; ");
    Serial.println();
#endif
  }

  void setOutputPins(uint8_t mask) override {
    // bit 0 of the mask corresponds to _pin[0]
    // bit 1 of the mask corresponds to _pin[1]
    // bit 2 of the mask corresponds to _pin[2]
    // bit 3 of the mask corresponds to _pin[3]

    uint8_t A_state = (mask & 0b0011);
    bool A_dir = 0;
    uint16_t A_pwm = 0;  // off by default
    switch (A_state) {
      case 1:  // backward
        A_dir = 1;
        A_pwm = _pwm1_value;
        break;
      case 2:  // forward
        A_dir = 0;
        A_pwm = _pwm1_value;
        break;
    }

    uint8_t B_state = (mask & 0b1100) >> 2;
    bool B_dir = 0;
    uint16_t B_pwm = 0;  // off by default
    switch (B_state) {
      case 1:  // backward
        B_dir = 1;
        B_pwm = _pwm2_value;
        break;
      case 2:  // forward
        B_dir = 0;
        B_pwm = _pwm2_value;
        break;
    }

    digitalWrite(_dir1, A_dir);
    digitalWrite(_dir2, B_dir);

    analogWrite(_pwm1, A_pwm);
    analogWrite(_pwm2, B_pwm);
  }

private:
  const float _lookupTable[33] = {
    0.000, 0.049, 0.098, 0.147, 0.196, 0.243, 0.290, 0.337, 0.382, 0.427, 0.471,
    0.514, 0.555, 0.595, 0.634, 0.672, 0.707, 0.741, 0.773, 0.804, 0.832, 0.857,
    0.882, 0.904, 0.924, 0.941, 0.957, 0.970, 0.980, 0.989, 0.995, 0.999, 1.000
  };
  long _frequency;
  uint8_t _steps;
  uint8_t _dir1, _pwm1, _dir2, _pwm2;
  uint16_t _pwm1_value, _pwm2_value;
  uint16_t _pwmMaxValue;
};

#endif  // DUAL_H_BRIDGE_STEPPER_H
