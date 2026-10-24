#!/usr/bin/env python3
"""Envoltorio de compatibilidad: `python udemy_transcripts.py ...` sigue funcionando.

El código vive en el paquete `udemy_transcripts/`; el comando instalado es `udemy`.
Ver README.md para el uso y docs/ARQUITECTURA.md para el diseño.
"""

import sys

from udemy_transcripts.cli import main

if __name__ == "__main__":
    sys.exit(main())
