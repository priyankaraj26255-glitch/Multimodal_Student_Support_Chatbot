import logging


def setup_logging(level: str = "INFO") -> None:
    """Privacy-conscious logging: we log paths, status codes and ids – never message
    bodies, file contents, emails, tokens or query strings."""
    logging.basicConfig(level=level.upper(),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("google.genai").setLevel(logging.WARNING)
