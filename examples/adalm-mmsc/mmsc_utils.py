# Copyright (C) 2026 Analog Devices, Inc.
#
# SPDX short identifier: ADIBSD

import sys
import tkinter as tk
from tkinter import ttk

import serial.tools.list_ports  # type: ignore

DEFAULT_BAUD_RATE = 230400
DEFAULT_COM_PORT = "COM12"
DEFAULT_M2K_URI = "ip:192.168.2.1"


def scan_com_ports():
    """Scan for available COM ports without opening them."""
    ports = serial.tools.list_ports.comports()
    return [port.device for port in sorted(ports)]


def scan_m2k_devices():
    """Scan for available M2K devices."""
    import libm2k  # type: ignore

    try:
        contexts = libm2k.getAllContexts()
        return contexts if contexts else []
    except Exception:
        return []


def build_ad4080_uri(com_port, baud_rate=DEFAULT_BAUD_RATE):
    """Build a serial URI string for the AD4080."""
    return f"serial:{com_port},{baud_rate}"


class DeviceSelectionDialog:
    """Tkinter dialog for selecting an AD4080 COM port and optionally an M2K URI.

    Usage:
        result = DeviceSelectionDialog(include_m2k=True).show()
        if result is None:
            sys.exit(0)
        # result["com_port"] is always present
        # result["m2k_uri"] is present when include_m2k=True
    """

    def __init__(self, include_m2k=False):
        self.include_m2k = include_m2k
        self.result = None
        self.root = tk.Tk()
        self.root.title("Select Devices" if include_m2k else "Select AD4080 COM Port")
        self.root.geometry("400x200" if include_m2k else "350x150")

        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.pack(fill="both", expand=True)

        row = 0

        # AD4080 COM Port selection
        ttk.Label(main_frame, text="AD4080 COM Port:", font=("", 10)).grid(
            row=row, column=0, sticky="w", padx=5, pady=10
        )

        available_ports = scan_com_ports()
        if available_ports:
            self.com_port = tk.StringVar(
                value=DEFAULT_COM_PORT
                if DEFAULT_COM_PORT in available_ports
                else available_ports[0]
            )
            ttk.Combobox(
                main_frame,
                textvariable=self.com_port,
                values=available_ports,
                width=25,
                state="readonly",
            ).grid(row=row, column=1, sticky="w", padx=5)
        else:
            self.com_port = tk.StringVar(value=DEFAULT_COM_PORT)
            ttk.Entry(main_frame, textvariable=self.com_port, width=27).grid(
                row=row, column=1, sticky="w", padx=5
            )
        row += 1

        # M2K URI selection (optional)
        if include_m2k:
            ttk.Label(main_frame, text="M2K URI:", font=("", 10)).grid(
                row=row, column=0, sticky="w", padx=5, pady=10
            )

            available_m2k = scan_m2k_devices()
            if available_m2k:
                self.m2k_uri = tk.StringVar(value=available_m2k[0])
                ttk.Combobox(
                    main_frame,
                    textvariable=self.m2k_uri,
                    values=available_m2k,
                    width=25,
                    state="readonly",
                ).grid(row=row, column=1, sticky="w", padx=5)
            else:
                self.m2k_uri = tk.StringVar(value=DEFAULT_M2K_URI)
                ttk.Entry(main_frame, textvariable=self.m2k_uri, width=27).grid(
                    row=row, column=1, sticky="w", padx=5
                )
            row += 1

        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=row, column=0, columnspan=2, pady=20)

        ttk.Button(button_frame, text="Connect", command=self.on_ok, width=12).pack(
            side="left", padx=5
        )
        ttk.Button(button_frame, text="Cancel", command=self.on_cancel, width=12).pack(
            side="left", padx=5
        )

    def on_ok(self):
        self.result = {"com_port": self.com_port.get()}
        if self.include_m2k:
            self.result["m2k_uri"] = self.m2k_uri.get()
        self.root.quit()
        self.root.destroy()

    def on_cancel(self):
        self.root.quit()
        self.root.destroy()

    def show(self):
        self.root.mainloop()
        return self.result
