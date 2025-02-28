# The MIT License (MIT)
# Copyright (c) 2022 Microsoft Corporation

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import unittest
import uuid
import time
import pytest

from azure.cosmos.aio import CosmosClient
import azure.cosmos.exceptions as exceptions
from azure.cosmos.http_constants import StatusCodes
import test_config
from azure.cosmos.partition_key import PartitionKey


pytestmark = pytest.mark.cosmosEmulator


# IMPORTANT NOTES:

#  	Most test cases in this file create collections in your Azure Cosmos account.
#  	Collections are billing entities.  By running these test cases, you may incur monetary costs on your account.

#  	To Run the test, replace the two member fields (masterKey and host) with values
#   associated with your Azure Cosmos account.

#   In order for the analytical ttl tests to work you have to enable Azure Synapse Link for your Azure Cosmos DB
#   account.


@pytest.mark.usefixtures("teardown")
class Test_ttl_tests(unittest.TestCase):
    """TTL Unit Tests.
    """

    host = test_config._test_config.host
    masterKey = test_config._test_config.masterKey
    connectionPolicy = test_config._test_config.connectionPolicy

    def __AssertHTTPFailureWithStatus(self, status_code, func, *args, **kwargs):
        """Assert HTTP failure with status.

        :Parameters:
            - `status_code`: int
            - `func`: function
        """
        try:
            func(*args, **kwargs)
            self.assertFalse(True, 'function should fail.')
        except exceptions.CosmosHttpResponseError as inst:
            self.assertEqual(inst.status_code, status_code)

    @classmethod
    async def setUpClass(cls):
        if (cls.masterKey == '[YOUR_KEY_HERE]' or
                cls.host == '[YOUR_ENDPOINT_HERE]'):
            raise Exception(
                    "You must specify your Azure Cosmos account values for "
                    "'masterKey' and 'host' at the top of this class to run the "
                    "tests.")
        cls.client = CosmosClient(cls.host, cls.masterKey, consistency_level="Session",
                                                connection_policy=cls.connectionPolicy)
        cls.created_db = await cls.client.create_database_if_not_exists("TTL_tests_database" + str(uuid.uuid4()))

    async def test_collection_ttl_replace_values(self):
        created_collection = await self.created_db.create_container_if_not_exists(
            id='test_ttl_values1' + str(uuid.uuid4()),
            partition_key=PartitionKey(path='/id'),
            analytical_storage_ttl=-1)
        await self.created_db.replace_container(created_collection, partition_key=PartitionKey(path='/id'),
                                          analytical_storage_ttl=1000)
        created_collection_properties = await created_collection.read()
        self.assertEqual(created_collection_properties['analyticalStorageTtl'], 1000)

        await self.created_db.delete_container(container=created_collection)

    async def test_collection_and_document_ttl_values(self):
        ttl = 10
        created_collection = await self.created_db.create_container_if_not_exists(
            id='test_ttl_values1' + str(uuid.uuid4()),
            partition_key=PartitionKey(path='/id'),
            analytical_storage_ttl=ttl)
        created_collection_properties = await created_collection.read()
        self.assertEqual(created_collection_properties['analyticalStorageTtl'], ttl)

        collection_id = 'test_ttl_values4' + str(uuid.uuid4())
        ttl = -10

        # -10 is an unsupported value for ttl. Valid values are -1 or a non-zero positive 32-bit integer value
        self.__AssertHTTPFailureWithStatus(
            StatusCodes.BAD_REQUEST,
            await self.created_db.create_container,
            collection_id,
            PartitionKey(path='/id'),
            None,
            ttl)

        document_definition = {'id': 'doc1' + str(uuid.uuid4()),
                               'name': 'sample document',
                               'key': 'value',
                               'ttl': 0}

        # 0 is an unsupported value for ttl. Valid values are -1 or a non-zero positive 32-bit integer value
        self.__AssertHTTPFailureWithStatus(
            StatusCodes.BAD_REQUEST,
            created_collection.create_item,
            document_definition)

        document_definition['id'] = 'doc2' + str(uuid.uuid4())
        document_definition['ttl'] = None

        # None is an unsupported value for ttl. Valid values are -1 or a non-zero positive 32-bit integer value
        self.__AssertHTTPFailureWithStatus(
            StatusCodes.BAD_REQUEST,
            await created_collection.create_item,
            document_definition)

        await self.created_db.delete_container(container=created_collection)

    async def test_document_ttl_with_positive_analyticalStorageTtl(self):
        created_collection = await self.created_db.create_container_if_not_exists(
            id='test_ttl_values3' + str(uuid.uuid4()),
            partition_key=PartitionKey(path='/id'),
            analytical_storage_ttl=5)

        document_definition = {'id': 'doc1' + str(uuid.uuid4()),
                               'name': 'sample document',
                               'key': 'value'}

        created_document = await created_collection.create_item(body=document_definition)

        document_definition['id'] = 'doc2' + str(uuid.uuid4())
        document_definition['ttl'] = -1
        created_document = await created_collection.create_item(body=document_definition)

        time.sleep(5)

        # the created document should NOT be gone as its ttl value is set to -1(never expire) which overrides the
        # collection's analyticalStorageTtl value
        read_document = await created_collection.read_item(item=document_definition['id'],
                                                     partition_key=document_definition['id'])
        self.assertEqual(created_document['id'], read_document['id'])

        document_definition['id'] = 'doc3' + str(uuid.uuid4())
        document_definition['ttl'] = 2
        created_document = await created_collection.create_item(body=document_definition)

        document_definition['id'] = 'doc4' + str(uuid.uuid4())
        document_definition['ttl'] = 8
        created_document = await created_collection.create_item(body=document_definition)

        time.sleep(6)

        # the created document should NOT be gone as its ttl value is set to 8 which overrides the collection's
        # analyticalStorageTtl value(5)
        read_document = await created_collection.read_item(item=created_document['id'], partition_key=created_document['id'])
        self.assertEqual(created_document['id'], read_document['id'])

        time.sleep(4)

        await self.created_db.delete_container(container=created_collection)

    async def test_document_ttl_with_negative_one_analyticalStorageTtl(self):
        created_collection = await self.created_db.create_container_if_not_exists(
            id='test_ttl_values4' + str(uuid.uuid4()),
            partition_key=PartitionKey(path='/id'),
            analytical_storage_ttl=-1)

        document_definition = {'id': 'doc1' + str(uuid.uuid4()),
                               'name': 'sample document',
                               'key': 'value'}

        # the created document's ttl value would be -1 inherited from the collection's analyticalStorageTtl and this
        # document will never expire
        created_document1 = await created_collection.create_item(body=document_definition)

        # This document is also set to never expire explicitly
        document_definition['id'] = 'doc2' + str(uuid.uuid4())
        document_definition['ttl'] = -1
        created_document2 = await created_collection.create_item(body=document_definition)

        document_definition['id'] = 'doc3' + str(uuid.uuid4())
        document_definition['ttl'] = 2

        # The documents with id doc1 and doc2 will never expire
        read_document = await created_collection.read_item(item=created_document1['id'],
                                                     partition_key=created_document1['id'])
        self.assertEqual(created_document1['id'], read_document['id'])

        read_document = await created_collection.read_item(item=created_document2['id'],
                                                     partition_key=created_document2['id'])
        self.assertEqual(created_document2['id'], read_document['id'])

        await self.created_db.delete_container(container=created_collection)

    async def test_document_ttl_with_no_analyticalStorageTtl(self):
        created_collection = await self.created_db.create_container_if_not_exists(
            id='test_ttl_no_analyticalStorageTtl' + str(uuid.uuid4()),
            partition_key=PartitionKey(path='/id', kind='Hash')
        )

        document_definition = {'id': 'doc1' + str(uuid.uuid4()),
                               'name': 'sample document',
                               'key': 'value',
                               'ttl': 5}

        created_document = await created_collection.create_item(body=document_definition)

        time.sleep(7)

        # Created document still exists even after ttl time has passed since the TTL is disabled at collection level
        # (no analyticalStorageTtl property defined)
        read_document = await created_collection.read_item(item=created_document['id'], partition_key=created_document['id'])
        self.assertEqual(created_document['id'], read_document['id'])

        await self.created_db.delete_container(container=created_collection)

    async def test_document_ttl_misc(self):
        created_collection = await self.created_db.create_container_if_not_exists(
            id='test_ttl_values5' + str(uuid.uuid4()),
            partition_key=PartitionKey(path='/id'),
            analytical_storage_ttl=8)

        document_definition = {'id': 'doc1' + str(uuid.uuid4()),
                               'name': 'sample document',
                               'key': 'value'}

        # We can create a document with the same id after the ttl time has expired
        await created_collection.create_item(body=document_definition)
        created_document = await created_collection.read_item(document_definition['id'], document_definition['id'])
        self.assertEqual(created_document['id'], document_definition['id'])

        time.sleep(3)

        # Upsert the document after 3 secs to reset the document's ttl
        document_definition['key'] = 'value2'
        upserted_docment = await created_collection.upsert_item(body=document_definition)

        time.sleep(7)

        # Upserted document still exists after 10 secs from document creation time(with collection's
        # analyticalStorageTtl set to 8) since its ttl was reset after 3 secs by upserting it
        read_document = await created_collection.read_item(item=upserted_docment['id'], partition_key=upserted_docment['id'])
        self.assertEqual(upserted_docment['id'], read_document['id'])

        time.sleep(3)

        documents = [document async for document in created_collection.query_items(
            query='SELECT * FROM root r',
            enable_cross_partition_query=True
        )]

        self.assertEqual(1, len(documents))

        # Removes analyticalStorageTtl property from collection to disable ttl at collection level
        replaced_collection = await self.created_db.replace_container(
            container=created_collection,
            partition_key=PartitionKey(path='/id', kind='Hash'),
            analytical_storage_ttl=None
        )

        document_definition['id'] = 'doc2' + str(uuid.uuid4())
        created_document = await created_collection.create_item(body=document_definition)

        time.sleep(5)

        # Created document still exists even after ttl time has passed since the TTL is disabled at collection level
        read_document = await created_collection.read_item(item=created_document['id'], partition_key=created_document['id'])
        self.assertEqual(created_document['id'], read_document['id'])

        await self.created_db.delete_container(container=created_collection)


if __name__ == '__main__':
    try:
        unittest.main()
    except SystemExit as inst:
        if inst.args[0] is True:  # raised by sys.exit(True) when tests failed
            raise
