"""
src.opentrons_sdk.constants

Common HTTP constants for Opentrons

Author(s):
    Paul MacNichol (paul.macnichol@qatchtech.com)

Date:
    2026-02-02

Version:
    0.1.0
"""


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
