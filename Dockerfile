FROM python:3.13-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY proofdeck ./proofdeck
RUN pip install --no-cache-dir .
ENV DATABASE_URL=sqlite:////data/proofdeck.db
VOLUME /data
EXPOSE 8000
CMD ["proofdeck", "serve", "--host", "0.0.0.0", "--port", "8000"]
