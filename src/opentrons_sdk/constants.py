import enum
from enum import Enum


class APIDefaults:
    PORT = 31950
    VERSION_HEADER = {"Opentrons-Version": "*", "Content-Type": "application/json"}
    DEFAULT_TIMEOUT = 30


class StatusCodes:
    OK = 200
    CREATED = 201
    ACCEPTED = 202
    NO_CONTENT = 204
    BAD_REQUEST = 400
    UNAUTHORIZED = 401
    NOT_FOUND = 404
    CONFLICT = 409
    UNPROCESSABLE_ENTITY = 422
    INTERNAL_SERVER_ERROR = 500


class Endpoints:
    # DELETE endpoints
    DELETE_WIFI_KEYS = "/wifi/keys/{key_uuid}"

    # GET endpoints
    GET_NETWORKING_STATUS = "/networking/status"
    GET_WIFI_LIST = "/wifi/list"
    GET_WIFI_CONFIGURE = "/wifi/configure"
    GET_WIFI_KEYS = "/wifi/keys"
    GET_WIFI_EAP_OPTIONS = "/wifi/eap-options"
    GET_ROBOT_POSITIONS = "/robot/positions"
    GET_ROBOT_LIGHTS = "/robot/lights"

    # POST endpoints
    POST_WIFI_KEYS = "/wifi/keys"
    POST_WIFI_DISCONNECT = "/wifi/disconnect"
    POST_IDENTIFY = "/identify"
    POST_ROBOT_MOVE = "/robot/move"
    POST_ROBOT_HOME = "/robot/home"
    POST_ROBOT_LIGHTS = "/robot/lights"
    POST_SETTINGS = "/robot/settings"

    # PUT endpoints
