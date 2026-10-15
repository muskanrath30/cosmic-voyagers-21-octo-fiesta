FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PORT=8080

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Manufacturing models are not committed (see .gitignore), so build them here.
# 1) AI4I is downloaded from UCI (best effort: the build continues without it,
#    and machine_tool is then scored by the flagged heuristic fallback).
# 2) Every asset that has data is trained and written to manufacturing/models/.
#    Commit manufacturing/data/samples/ (metropt_sample.csv, cwru_sample.npz)
#    so the compressor and bearing models train on real data, not stand-ins.
RUN python manufacturing/download_dataset.py || echo "AI4I download skipped"
RUN python -c "from manufacturing.train import ensure_models; print('trained:', ensure_models())"

RUN useradd --create-home appuser && chown -R appuser /app
USER appuser

EXPOSE 8080

CMD ["python", "main.py"]
