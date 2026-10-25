"""
Translation engine adapters for the Twi Translation Benchmark Lab.

Available adapters:
    OPUSMTAdapter — local MarianMT inference (no internet required, GPU optional).
    KhayaAdapter  — cloud Khaya translation API (internet + API key required).

Both adapters implement the EngineAdapter abstract base class and return a
standardised TranslationResult that is compatible with the ExperimentRun schema.

Importing this package does NOT download any models or call any APIs.
"""

from twi_lab.engines.base import EngineAdapter
from twi_lab.engines.khaya import KhayaAdapter
from twi_lab.engines.opus_mt import OPUSMTAdapter

__all__ = ["EngineAdapter", "OPUSMTAdapter", "KhayaAdapter"]
