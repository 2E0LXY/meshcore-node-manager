#!/usr/bin/env python3
"""
main.py — entry point for MeshCore Node Manager
"""
from version import VERSION_STR
from app import AppWindow

if __name__ == "__main__":
    print(f"MeshCore Node Manager {VERSION_STR}")
    AppWindow().mainloop()
