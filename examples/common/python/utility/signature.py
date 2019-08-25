# Copyright 2019 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
signature.py -- functions to perform hash calculation and signature generation and verification
functions based on Spec 1.0 compatibility

"""

import base64
import os
import sys
import json
import urllib.request
import urllib.error
import random
import json
import logging
import crypto.crypto as crypto
import utility.file_utils as putils
import utility.utility as utility
import worker.worker_details as worker
from error_code.error_status import SignatureStatus

logger = logging.getLogger(__name__)
#No of bytes of encrypted session key to encrypt data
NO_OF_BYTES = 16

class ClientSignature(object) :
    """
    Class to perform hash calculation, signature generation and verification
    """

    def __init__(self):
        self.private_key = None
        self.public_key = None
        self.param_pool = ["requesterNonce", "workOrderId", "workerId", "requesterId","inData"]
        self.tcs_worker = utility.read_toml_file("tcs_config.toml","WorkerConfig")

#---------------------------------------------------------------------------------------------
    def __payload_json_check(self, json_data):
        """
        Function to check if mandatory parameters are available as per param_pool
        Parameters:
            - json_data is a work order submit request json as per TCF API 6.1.1 Work Order Request Payload
        """

        data = json.loads(json_data)
        if 'params' not in data:
            logger.error("ERROR: Worker Order Submit Json does not have the required params")
            return False

        data_params = data['params']
        param_valid = True;
        for param in self.param_pool:
            if ( param not in data_params ):
                #List down all the missing Parameters
                logger.error("ERROR: Worker Order Submit Json does not have the required parameter: %s", param)
                param_valid  = False

        if param_valid:
            i_obj = data_params['inData']
            for obj in i_obj :
                if 'data' not in obj or not obj["data"] or 'index' not in obj:
                    logger.error("ERROR: Worker Order Submit Json does not have the required parameter in InData")
                    param_valid  = False

        return param_valid

#---------------------------------------------------------------------------------------------
    def __encrypt_workorder_indata(self, input_json_params,
            session_key, session_iv, worker_encryption_key, data_key=None, data_iv=None):
        """
        Function to encrypt inData of workorder
        Parameters:
            - input_json_params is inData and outData elements within work order
              request as per TCF API 6.1.7 Work Order Data Formats
            - session_key is a one-time encryption key generated by the
              participant submitting the work order.
            - session_iv is an initialization vector if required by the
              data encryption algorithm (encryptedSessionKey). The default is all zeros.
            - data_key is a one time key generated by participant used to encrypt
              work order indata
            - data_iv is an intialization vector used along with data_key.
              Default is all zeros.
        """

        indata_objects = input_json_params['inData']
        indata_objects.sort(key=lambda x: x['index'])
        input_json_params['inData'] = indata_objects
        logger.info("Encrypting Workorder Data");

        i = 0
        for item in indata_objects:
            data = item['data'].encode('UTF-8')
            e_key = item['encryptedDataEncryptionKey'].encode('UTF-8')

            if (not e_key ) or (e_key == "null".encode('UTF-8')):
                enc_data = utility.encrypt_data(data, session_key, session_iv)
                input_json_params['inData'][i]['data'] = crypto.byte_array_to_base64(enc_data)
                logger.debug("encrypted indata - %s", crypto.byte_array_to_base64(enc_data))
            elif e_key == "-".encode('UTF-8'):
                # Skip encryption and just encode workorder data to base64 format
                input_json_params['inData'][i]['data'] = crypto.byte_array_to_base64(data)
            else:
                enc_data = utility.encrypt_data(data, data_key, data_iv)
                input_json_params['inData'][i]['data'] = crypto.byte_array_to_base64(enc_data)
                logger.debug("encrypted indata - %s", crypto.byte_array_to_base64(enc_data))
            i = i + 1

        logger.debug("Workorder InData after encryption: %s", indata_objects)

#---------------------------------------------------------------------------------------------
    def __calculate_hash_on_concatenated_string(self, input_json_params, nonce_hash):
        """
        Function to calculate a hash value of the string concatenating the following values:
        requesterNonce, workOrderId, workerId, workloadId, and requesterId.
        Parameters:
            - input_json_params is a collection of parameters as per TCF APi 6.1.1 Work Order Request Payload
            - nonce_hash is SHA256 hashed value of a random string generated by the participant.
        """

        workorder_id = (input_json_params['workOrderId']).encode('UTF-8')
        worker_id = (input_json_params['workerId']).encode('UTF-8')
        workload_id = "".encode('UTF-8')
        if 'workloadId' in input_json_params :
            workload_id = (input_json_params['workloadId']).encode('UTF-8')
        requester_id = (input_json_params['requesterId']).encode('UTF-8')

        concat_string = nonce_hash + workorder_id + worker_id + workload_id + requester_id
        concat_hash =  bytes(concat_string)
        #SHA-256 hashing is used
        hash_1 = crypto.compute_message_hash(concat_hash)
        result_hash = crypto.byte_array_to_base64(hash_1)

        return result_hash

#---------------------------------------------------------------------------------------------
    def __calculate_datahash(self, data_objects):
        """
        Function to calculate a hash value of the array concatenating dataHash, data,
        encryptedDataEncryptionKey, iv for each item in the inData/outData array
        Parameters:
            - data_objects is each item in inData or outData part of workorder request as per TCF API 6.1.7 Work Order Data Formats
        """

        hash_str = ""
        for item in data_objects:
            datahash = "".encode('UTF-8')
            if 'dataHash' in item:
                datahash = item['dataHash'].encode('UTF-8')
            data = item['data'].encode('UTF-8')
            e_key = item['encryptedDataEncryptionKey'].encode('UTF-8')
            iv = item['iv'].encode('UTF-8')
            concat_string =  datahash + data + e_key + iv
            concat_hash = bytes(concat_string)
            hash = crypto.compute_message_hash(concat_hash)
            hash_str = hash_str + crypto.byte_array_to_base64(hash)

        return hash_str
#---------------------------------------------------------------------------------------------
    def __generate_signature(self, hash, private_key):
        """
        Function to generate signature object
        Parameters:
            - hash is the combined array of all hashes calculated on the message
            - private_key is Client private key
        """

        self.private_key = private_key
        self.public_key =  self.private_key.GetPublicKey().Serialize()
        signature_result =  self.private_key.SignMessage(hash)
        signature_base64  =  crypto.byte_array_to_base64(signature_result)
        return  signature_base64

#---------------------------------------------------------------------------------------------
    def generate_client_signature(self, input_json_str,
            worker, private_key, session_key, session_iv, encrypted_session_key,
            data_key=None, data_iv=None):
        """
        Function to generate client signature
        Parameters:
            - input_json_str is requester Work Order Request payload in a
              JSON-RPC based format defined 6.1.1 Work Order Request Payload
            - worker is a worker object to store all the common details of
              worker as per TCF API 8.1 Common Data for All Worker Types
            - private_key is Client private key
            - session_key is one time session key generated by the participant
              submitting the work order.
            - session_iv is an initialization vector if required by the
              data encryption algorithm (encryptedSessionKey). The default is all zeros.
            - data_key is a one time key generated by participant used to encrypt
              work order indata
            - data_iv is an intialization vector used along with data_key.
              Default is all zeros.
            - encrypted_session_key is a encrypted version of session_key.
        """

        if (self.__payload_json_check(input_json_str) is False):
            logger.error("ERROR: Signing the request failed")
            return None

        if (self.tcs_worker['HashingAlgorithm'] !=  worker.hashing_algorithm ):
            logger.error("ERROR: Signing the request failed. Hashing algorithm is not supported for %s", worker.hashing_algorithm )
            return None

        if (self.tcs_worker['SigningAlgorithm'] !=  worker.signing_algorithm):
            logger.error("ERROR: Signing the request failed. Signing algorithm is not supported for %s", worker.signing_algorithm )
            return None

        input_json = json.loads(input_json_str)
        input_json_params = input_json['params']
        input_json_params["sessionKeyIv"] = ''.join(format(i, '02x') for i in session_iv)

        encrypted_session_key_str = ''.join(format(i, '02x') for i in encrypted_session_key)
        self.__encrypt_workorder_indata(input_json_params, session_key,
                session_iv, worker.worker_encryption_key, data_key, data_iv)
        # [NO_OF_BYTES] 16 BYTES for nonce, is the recommendation by NIST to
        # avoid collisions by the "Birthday Paradox".
        nonce =  crypto.random_bit_string(NO_OF_BYTES)

        request_nonce_hash = crypto.compute_message_hash(nonce)
        nonce_hash = (crypto.byte_array_to_base64(request_nonce_hash)).encode('UTF-8')
        hash_string_1 = self.__calculate_hash_on_concatenated_string(input_json_params, nonce_hash)
        data_objects = input_json_params['inData']
        hash_string_2 = self.__calculate_datahash(data_objects)

        hash_string_3 = ""
        if 'outData' in input_json_params:
            data_objects = input_json_params['outData']
            data_objects.sort(key = lambda x:x['index'])
            hash_string_3 = self.__calculate_datahash(data_objects)

        concat_string = hash_string_1 + hash_string_2 + hash_string_3
        concat_hash = bytes(concat_string, 'UTF-8')
        final_hash = crypto.compute_message_hash(concat_hash)

        encrypted_request_hash = utility.encrypt_data(final_hash, session_key, session_iv)
        encrypted_request_hash_str = ''.join(format(i, '02x') for i in encrypted_request_hash)
        logger.debug("encrypted request hash: \n%s", encrypted_request_hash_str)

        #Update the input json params
        input_json_params["encryptedRequestHash"] = encrypted_request_hash_str
        input_json_params['requesterSignature'] = self.__generate_signature(final_hash, private_key)
        input_json_params["encryptedSessionKey"] = encrypted_session_key_str
        # Temporary mechanism to share client's public key. Not a part of Spec
        input_json_params['verifyingKey'] =  self.public_key
        input_json_params['requesterNonce'] = crypto.byte_array_to_base64(request_nonce_hash)
        input_json['params'] = input_json_params
        input_json_str = json.dumps(input_json)
        logger.info("Request Json successfully Signed")

        return input_json_str

#---------------------------------------------------------------------------------------------
    def verify_signature(self,response_str,worker):
        """
        Function to verify the signature received from the enclave
        Parameters:
            - response_str is json payload returned by the Worker Service in response to successful workorder submit request as per TCF API 6.1.2 Work Order Result Payload
            - worker is a worker object to store all the common details of worker as per TCF API 8.1 Common Data for All Worker Types
        """

        input_json = json.loads(response_str)

        if ( self.tcs_worker['HashingAlgorithm'] !=  worker.hashing_algorithm ):
            logger.error("ERROR: Signing the request failed. Hashing algorithm is not supported for %s", worker.hashing_algorithm )
            return SignatureStatus.ERROR_RESPONSE

        if ( self.tcs_worker['SigningAlgorithm'] !=  worker.signing_algorithm):
            logger.error("ERROR: Signing the request failed. Signing algorithm is not supported for %s", worker.signing_algorithm )
            return SignatureStatus.ERROR_RESPONSE

        #Checking for a error response.
        if  'error' in input_json.keys():
            return SignatureStatus.ERROR_RESPONSE

        input_json_params = input_json['result']

        #Checking if error is response
        if  'code' in input_json_params.keys() and input_json_params['code'] < 0 :
            return SignatureStatus.ERROR_RESPONSE

        nonce = (input_json_params['workerNonce']).encode('UTF-8')
        signature = input_json_params['workerSignature']

        hash_string_1 = self.__calculate_hash_on_concatenated_string(input_json_params, nonce)
        data_objects = input_json_params['outData']
        data_objects.sort(key = lambda x:x['index'])
        hash_string_2 = self.__calculate_datahash(data_objects)
        concat_string =  hash_string_1+ hash_string_2
        concat_hash = bytes(concat_string, 'UTF-8')
        final_hash = crypto.compute_message_hash(concat_hash)

        verify_key = worker.worker_typedata_verification_key

        try:
            _verifying_key = crypto.SIG_PublicKey(verify_key)
        except Exception as error:
            logger.info("Error in verification key : %s", error)
            return SignatureStatus.INVALID_VERIFICATION_KEY

        decoded_signature = crypto.base64_to_byte_array(signature)
        sig_result =_verifying_key.VerifySignature(final_hash, decoded_signature)

        if sig_result == 1 :
            return SignatureStatus.PASSED
        elif sig_result == 0 :
            return SignatureStatus.FAILED
        else :
            return SignatureStatus.INVALID_SIGNATURE_FORMAT

#---------------------------------------------------------------------------------------------

