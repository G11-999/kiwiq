# docker build -t py-runner:3.12 -f untrusted_code_runner/Dockerfile untrusted_code_runner
FROM python:3.12-slim

# Speed & determinism
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Security: non-root user
RUN useradd -u 10001 -m sandbox

# ---- Fixed deps (SAME for all jobs) ----
# Put your global, pre-approved packages here (pin versions!)
# If you want *only* stdlib, you can remove this block entirely.
COPY requirements-base.txt /tmp/requirements-base.txt
RUN pip install --no-cache-dir -r /tmp/requirements-base.txt

# Runner entrypoint
COPY runner.py /usr/local/bin/runner.py

USER sandbox
WORKDIR /work
ENTRYPOINT ["python","/usr/local/bin/runner.py"]
