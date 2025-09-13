# Calculadora de BrAC/BAC — Streamlit + Docker

## Uso rápido
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Docker
```bash
docker build -t brac-app .
docker run --rm -p 8501:8501 brac-app
```

## Notas
- Asegúrate de que `alcohol_test3.py` está en la raíz del proyecto.
- Edita `.streamlit/config.toml` para el tema visual.
