"""Pydantic request/response models for the MakeBlock Explorer API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ConnectRequest(BaseModel):
    port: str


class DisconnectRequest(BaseModel):
    device_id: str


class CommandRequest(BaseModel):
    device_id: str
    script: str


class LedRequest(BaseModel):
    device_id: str
    red: int = Field(..., ge=0, le=255)
    green: int = Field(..., ge=0, le=255)
    blue: int = Field(..., ge=0, le=255)
    led_id: int | None = Field(None, ge=1, le=5)


class NotifyRequest(BaseModel):
    device_id: str
    text: str = Field(..., max_length=30)
    color: list[int] = Field(default=[255, 255, 255])
    size: int = Field(default=24, ge=12, le=48)
    flash_leds: bool = Field(default=True)


class DeviceInfoResponse(BaseModel):
    port: str
    description: str
    vid: int | None
    pid: int | None


class DeviceStatusResponse(BaseModel):
    device_id: str
    port: str
    device_type: str
    is_connected: bool
    sensor_cache: dict
