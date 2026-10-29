Add one reviewed release request per JSON file here. The filename must match its release_id.

Existing release requests cannot be edited or deleted through the normal workflow. Create a new release ID for a new attempt with different inputs. Retrying an identical request reuses its idempotency token.

Do not put credentials, prompts or model weights in a release request. Use the example in ../examples/release-request.json and replace every example value with actual reviewed evidence.
