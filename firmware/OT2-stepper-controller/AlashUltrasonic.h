#ifndef AlashUltrasonic_H
#define AlashUltrasonic_H

#include <Arduino.h>
#include <Wire.h>
#include <SoftwareSerial.h>

// Enum для типов подключения
enum ConnectionType {
  GPIO_MODE,
  I2C_MODE,
  UART_MODE,
  ONEWIRE_MODE
};

class AlashUltrasonic {
  public:
    // Конструкторы для разных типов подключения
    AlashUltrasonic(uint8_t triggerPin, uint8_t echoPin);  // GPIO
    AlashUltrasonic(uint8_t i2cAddress);                   // I2C
    AlashUltrasonic(uint8_t rxPin, uint8_t txPin, ConnectionType type); // UART с явным указанием типа
    AlashUltrasonic(uint8_t oneWirePin, ConnectionType type); // 1-Wire с явным указанием типа

    // Инициализация
    void begin();
    
    // Измерение расстояния
    float getDistance();
  
  private:
    // Переменные для GPIO
    uint8_t _triggerPin;
    uint8_t _echoPin;
    
    // Переменные для I2C
    uint8_t _i2cAddress;
    
    // Переменные для UART
    SoftwareSerial* _serial;
    uint8_t _rxPin;
    uint8_t _txPin;
    
    // Переменные для 1-Wire
    uint8_t _oneWirePin;

    // Общие переменные
    ConnectionType _connectionType;
    unsigned long _lastReadTime;
    
    // Внутренние функции для измерения расстояния
    float getDistanceGPIO();
    float getDistanceI2C();
    float getDistanceUART();
    float getDistanceOneWire();
    float calculateDistance(long duration);
};

#endif
