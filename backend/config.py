import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


class Settings:
    JSONBIN_API_KEY: str = os.getenv("JSONBIN_API_KEY", "")
    JSONBIN_BIN_ID: str = os.getenv("JSONBIN_BIN_ID", "")
    GLM_API_KEY: str = os.getenv("GLM_API_KEY", "")
    GLM_BASE_URL: str = os.getenv("GLM_BASE_URL", "")
    GLM_MODEL_NAME: str = os.getenv("GLM_MODEL_NAME", "ilmu-glm-5.1")
    JSONBIN_BASE_URL: str = "https://api.jsonbin.io/v3"
    FASTAPI_HOST: str = "0.0.0.0"
    FASTAPI_PORT: int = 8000
    DATA_DIR: Path = Path(__file__).resolve().parent.parent / "data"
    QUOTES_DIR: Path = Path(__file__).resolve().parent.parent / "data" / "quotes"

    def validate_required(self) -> list[str]:
        missing = []
        if not self.JSONBIN_API_KEY:
            missing.append("JSONBIN_API_KEY")
        if not self.GLM_API_KEY:
            missing.append("GLM_API_KEY")
        if not self.GLM_BASE_URL:
            missing.append("GLM_BASE_URL")
        return missing


settings = Settings()
