FROM amazon/aws-lambda-python:3.11

# Copy function code
COPY lambda_function.py ${LAMBDA_TASK_ROOT}

# Copy and install requirements
COPY requirements.txt .
RUN pip install -r requirements.txt --target "${LAMBDA_TASK_ROOT}"

# Command can be overwritten by providing a different command in the template directly.
CMD ["lambda_function.lambda_handler"]
