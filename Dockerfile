FROM python:3.14-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        dosfstools \
        file \
        gdisk \
        genisoimage \
        parted \
        rsync \
        util-linux \
        wimlib \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY pyproject.toml README.md LICENSE ./
COPY py_burn ./py_burn
RUN pip install --no-cache-dir --no-deps .

ENTRYPOINT ["py_burn"]
