class AnimeStudioError(Exception):
    """Base exception class for all Anime Studio errors."""


class ToolNotFoundError(AnimeStudioError):
    """Exception raised when a required external binary is not found."""


class ToolExecutionError(AnimeStudioError):
    """Exception raised when an external binary fails to execute or returns an error."""


class ConfigurationError(AnimeStudioError):
    """Exception raised when application configuration is invalid or missing."""


class FontMatchError(AnimeStudioError):
    """Exception raised when font resolution chain is fully exhausted."""


class HunterError(AnimeStudioError):
    """Exception raised when an individual hunter source fails."""


class EncodingRepairError(AnimeStudioError):
    """Exception raised when subtitle encoding repair fails or is unrecoverable."""
