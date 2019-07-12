from abc import ABC,abstractmethod

class WorkOrderInterface(ABC):
    """
    WorkOrderRegistryInterface is an abstract base class that contains
    abstract APIs to manage work orders
    """

    def __init__(self):
        super().__init__()

    @abstractmethod
    def work_order_submit(self, wo_request_json_str, in_data, out_data, id=None):
        """
        Submit work order request
        wo_request_json_str is json string containing following parameters
        {
            "responseTimeoutMSecs": <integer>,
            "payloadFormat": <string>
            "resultUri": <string>,
            "notifyUri": <string>,
            "workOrderId": <hex string>,
            "workerId": <hex string or DID>,
            "workloadId": <hex string>,
            "requesterId": <hex string>,
            "workerEncryptionKey": <hex string>,
            "dataEncryptionAlgorithm": <string>,
            "encryptedSessionKey": <hex string>,
            "sessionKeyIv": <hex string>,
            "requesterNonce": <hex string>,
            "encryptedRequestHash": <hex string>,
            "requesterSignature": <BASE64 string>,
        },
        in_data is an array of work order data objects, as defined below.
        "inData": [<object>],
        out_data is an array of work order output objects, as defined below.
        "outData": [<object>]
        1. responseTimeoutMsecs - is a maximum timeout in milliseconds that the caller will wait for
        the response. Setting this timeout to zero means that the work order is submitted in the
        asynchronous (resultUri is present), notify (notifyUri is present), or pull mode 
        (neither resultUri nor notifyUri is present). In this case, the TCS should schedule 
        the request for execution and immediately return an error response with error code 
        set to "scheduled". If the timeout is not zero, the work order is in synchronous mode.
        The TCS should wait for the work order completion before returning the response to the 
        participant. If the request cannot be completed within the allocated interval, the work order
        should be cancelled and a corresponding error should be returned to the participant.
        2. payloadFormat defines how signatures and data items are formatted in this work order 
        request and corresponding response.
        3. resultUri is an optional parameter. If it is specified, the WorkerService should submit
        the Work Order result to this URI. See section Work Order Asynchronous Result.
        4. notifyUri is an optional parameter. If it is specified, the WorkerService should send
        an event to this URI upon the Work Order completion.
        5. workOrderId is an id assigned to the Work Order by the Requester and can be registered 
        using the Work Order Receipts API.
        6. workerId is a worker id to process the work order, e.g. an Ethereum address or its DID.
        7. workloadId is an id of the workload to be executed by the worker. 
        It is an optional value if the worker includes a single workload.
        8. requesterId is either the Requester’s Ethereum address or its DID.
        9. workerEncryptionKey is an optional parameter containing the worker encryption key 
        used for this Work Order. It is useful if a Worker frequently updates its encryption key 
        in the registry and allows some time overlap in utilizing multiple keys. 
        We assume here that the 'details' submitted during the registration of a worker contain 
        one or more public keys associated with the worker.
        10. dataEncryptionAlgorithm is an optional parameter that defines an algorithm for encrypting
         the data in this work order. The default is the first value in the corresponding parameter 
         for the worker (defined by workerId). See section Common Data for All Worker Types.
        11. encryptedSessionKey is a one-time encryption key generated by the participant submitting 
        the work order. It is sent encrypted with the worker's public encryption key. 
        It is used to encrypt encryptedRequestHash and data item specific data encryption keys. 
        For the latter see Work Order Data Formats.
        12. sessionKeyIv is an initialization vector if required by the data encryption algorithm 
        (encryptedSessionKey). The default is all zeros.
        13. requesterNonce is a random string generated by the participant. 
        It is used to calculate a hash of this work order request.
        14. encryptedRequestHash is a hash of the work order request encrypted with the 
        key provided in encryptedSessionKey.
        15. requesterSignature is an optional parameter. See section Work Order Signing for the details.
        16. inData contains either a JWT of the specified data or an array of one or more 
        Work Order inputs, e.g. state, message containing input parameters.
        {
            "index": <number>,
            "dataHash": <hex string>,
            "data": <BASE64 string>,
            "encryptedDataEncryptionKey": <hex string>,
            "iv": <hex string>
        }
        i. index is an index that determines order of the data items for the hash generation. 
        It also can be used by the worker to identify different inputs and outputs.
        ii. dataHash is an optional hash value of the data. It is only applicable to inData 
        in the work order request and outData in the response.
        iii. data contains either data inline within the JSON document or a reference 
        (e.g. URI) to the data. It is up to the worker to determine how to interpret 
        the data content. This parameter is applicable to
            -> inData in the work order request
            -> outData in the request if it contains a reference for the output
            -> outData in the response
        iv. encryptedDataEncryptionKey defines if data are encrypted and what key to use. 
        It is included only in the work order request as one of the options below
        If this key is not provided or set to "null" or to "", the data is encrypted using 
        encryptedSessionKey from the work order request
        If the key value is set to "-", the data item is not encrypted, a.k.a. sent as clear text
        Otherwise, the data item is sent encrypted with a one-time encryption key generated by a 
        3rd party that owns this data item (it may be different from the work order requester). 
        encryptedDataEncryptionKey contains this encryption key in double encrypted format
        First, it is encrypted with the worker's public encryption key (e.g. by a 3rd party that owns 
        the data so the requester cannot see the data)
        Then the result of the previous encryption above is encrypted with the key from 
        encryptedSessionKey (by the requester to enforce the work order integrity)
        v. iv is an initialization vector if required by the data encryption algorithm. 
        The default is all zeros. If the same encryption key is used to encrypt more than one data 
        item or the hash value of the work order request, 
        iv must be a unique random number for every encryption operation. 
        It is included only in the work order request.
        17. outData contains information about what and how the work order execution results 
        should be delivered. Same as inData
        18. id is used for json rpc request
        """
        pass

    @abstractmethod
    def work_order_get_result(self, work_order_id, id=None):
        """
        Get worker order result
        If a Requester receives a response stating that its Work Order state is 
        "scheduled" or "processing", it should pull the Worker Service later to get the result.
        1. Pull the Worker Service periodically until the Work Order is completed successfully
        or in error
        2. Wait for the Work Order Receipt complete event and retrieve a final result.
        Inputs
        3. id is used for json rpc request
        work_order_id is a Work Order id that was sent in the corresponding work_order_submit request.

        """
        pass

