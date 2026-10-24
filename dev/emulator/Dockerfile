FROM python:3.13-alpine

# The emulator only uses the standard library, so no dependencies are installed.
WORKDIR /app

COPY emulator.py ./

# Telnet port of the emulated matrix.
EXPOSE 23

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python", "-u", "/app/emulator.py"]
