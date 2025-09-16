from app.core.config import get_settings
from app.main import app

s = get_settings()
print("quant_core_root =", s.quant_core_root)
print("App title       =", app.title)
print("Has quant_core_missing state =", hasattr(app.state, "quant_core_missing"))
