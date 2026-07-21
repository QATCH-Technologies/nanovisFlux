#include "AlashUltrasonic.h"

// Конструктор для GPIO
AlashUltrasonic::AlashUltrasonic(uint8_t triggerPin, uint8_t echoPin) {
  _triggerPin = triggerPin;
  _echoPin = echoPin;
  _connectionType = GPIO_MODE;
  _lastReadTime = 0;
}

// Конструктор для I2C
AlashUltrasonic::AlashUltrasonic(uint8_t i2cAddress) {
  _i2cAddress = i2cAddress;
  _connectionType = I2C_MODE;
  _lastReadTime = 0;
}

// Конструктор для UART
AlashUltrasonic::AlashUltrasonic(uint8_t rxPin, uint8_t txPin, ConnectionType type) {
  _rxPin = rxPin;
  _txPin = txPin;
  _connectionType = type;
  _lastReadTime = 0;
  _serial = new SoftwareSerial(_rxPin, _txPin);
}

// Конструктор для 1-Wire
AlashUltrasonic::AlashUltrasonic(uint8_t oneWirePin, ConnectionType type) {
  _oneWirePin = oneWirePin;
  _connectionType = type;
  _lastReadTime = 0;
}

// Инициализация
void AlashUltrasonic::begin() {
  switch (_connectionType) {
    case I2C_MODE:
      Wire.begin();
      break;
    case UART_MODE:
      _serial->begin(9600);
      break;
    case ONEWIRE_MODE:
      pinMode(_oneWirePin, OUTPUT);
      break;
    case GPIO_MODE:
    default:
      pinMode(_triggerPin, OUTPUT);
      pinMode(_echoPin, INPUT);
      break;
  }
}

// Измерение расстояния
float AlashUltrasonic::getDistance() {
  if (millis() - _lastReadTime < 30) {
    delay(millis() - _lastReadTime);
  }
  _lastReadTime = millis();

  switch (_connectionType) {
    case I2C_MODE:
      return getDistanceI2C();
    case UART_MODE:
      return getDistanceUART();
    case ONEWIRE_MODE:
      return getDistanceOneWire();
    case GPIO_MODE:
    default:
      return getDistanceGPIO();
  }
}

// Измерение расстояния через GPIO
float AlashUltrasonic::getDistanceGPIO() {
  digitalWrite(_triggerPin, HIGH);
  delayMicroseconds(500);
  digitalWrite(_triggerPin, LOW);

  long duration = pulseIn(_echoPin, HIGH);
  return calculateDistance(duration);
}

// Измерение расстояния через I2C
float AlashUltrasonic::getDistanceI2C() {
  Wire.beginTransmission(_i2cAddress);
  Wire.write(0x01);
  Wire.endTransmission();
  
  delay(150);

  byte response[3];
  Wire.requestFrom((uint8_t)_i2cAddress, (uint8_t)3);
  for (byte i = 0; Wire.available() && (i < 3); i++) {
    response[i] = Wire.read();
  }

  float micrometers = ((response[0] * 65536UL) + (response[1] * 256UL) + response[2]);
  return micrometers / 1000000.0 * 100.0;
}

// Измерение расстояния через UART
float AlashUltrasonic::getDistanceUART() {
  _serial->flush();
  _serial->write(0xA0);
  
  delay(150);
  
  byte response[3];
  for (byte i = 0; _serial->available() && (i < 3); i++) {
    response[i] = _serial->read();
  }
  
  float micrometers = ((response[0] * 65536UL) + (response[1] * 256UL) + response[2]);
  return micrometers / 1000000.0 * 100.0;
}

// Измерение расстояния через 1-Wire
float AlashUltrasonic::getDistanceOneWire() {
  pinMode(_oneWirePin, OUTPUT);
  digitalWrite(_oneWirePin, HIGH);
  delayMicroseconds(500);
  digitalWrite(_oneWirePin, LOW);

  pinMode(_oneWirePin, INPUT);
  long duration = pulseIn(_oneWirePin, HIGH);
  float distance = duration * 340.0 / 2.0 / 10000.0;
  return distance;
}

// Преобразование времени в расстояние
float AlashUltrasonic::calculateDistance(long duration) {
  float distance = (duration / 2.0) * 0.0343;
  return distance;
}
