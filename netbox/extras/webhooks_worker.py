import json

import requests
from django_rq import job
from rest_framework.utils.encoders import JSONEncoder

from .choices import ObjectChangeActionChoices, WebhookContentTypeChoices
from .webhooks import generate_signature


@job('default')
def process_webhook(webhook, data, model_name, event, timestamp, username, request_id):
    """
    Make a POST request to the defined Webhook
    """
    payload = {
        'event': dict(ObjectChangeActionChoices)[event].lower(),
        'timestamp': timestamp,
        'model': model_name,
        'username': username,
        'request_id': request_id,
        'data': data
    }
    headers = {
        'Content-Type': webhook.http_content_type,
    }
    if webhook.additional_headers:
        headers.update(webhook.additional_headers)

    params = {
        'method': 'POST',
        'url': webhook.payload_url,
        'headers': headers
    }

    if webhook.http_content_type == WebhookContentTypeChoices.CONTENTTYPE_JSON:
        params.update({'data': json.dumps(payload, cls=JSONEncoder)})
    elif webhook.http_content_type == WebhookContentTypeChoices.CONTENTTYPE_FORMDATA:
        params.update({'data': payload})

    prepared_request = requests.Request(**params).prepare()

    if webhook.secret != '':
        # Sign the request with a hash of the secret key and its content.
        prepared_request.headers['X-Hook-Signature'] = generate_signature(prepared_request.body, webhook.secret)

    with requests.Session() as session:
        session.verify = webhook.ssl_verification
        if webhook.ca_file_path:
            session.verify = webhook.ca_file_path
        response = session.send(prepared_request)

    if 200 <= response.status_code <= 299:
        return 'Status {} returned, webhook successfully processed.'.format(response.status_code)
    else:
        raise requests.exceptions.RequestException(
            "Status {} returned with content '{}', webhook FAILED to process.".format(
                response.status_code, response.content
            )
        )