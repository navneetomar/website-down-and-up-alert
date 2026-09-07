#!/bin/bash
cd "$(dirname "$0")"
export TK_SILENCE_DEPRECATION=1
open "http://localhost:3000"
exec /usr/bin/python3 web.py
