from .didallclient import DIDAllClient

from .did_wba import \
    create_did_wba_document, \
    resolve_did_wba_document, \
    resolve_did_wba_document_sync, \
    generate_auth_header, \
    verify_auth_header_signature, \
    extract_auth_header_parts

from .did_wba_auth_header import DIDWbaAuthHeader

# Define what should be exported when using "from agent_connect.authentication import *"
__all__ = ['DIDAllClient', \
           'create_did_wba_document', \
           'resolve_did_wba_document', \
           'resolve_did_wba_document_sync', \
           'generate_auth_header', \
           'verify_auth_header_signature', \
           'extract_auth_header_parts', \
           'DIDWbaAuthHeader']

