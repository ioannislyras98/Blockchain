from new_src.wallet import Wallet
from new_src.transaction import Transaction
from new_src.blockchain import Blockchain, minings
from new_src.block import Block
import time
import requests
import json
import threading


valLock = threading.Lock()

consFlag = threading.Event()
consFlag.set()

bcLock = threading.Lock()
class Node:
    def __init__(self, port, IP, nodeNr, bootstrap):
        self.port = port
        self.IP = IP
        self.addr = "http://" + self.IP + ":" + str(self.port)

        # Assuming bootstrap's always there
        self.bootstrapAddr = 'http://192.168.0.3:5000'
        self.bootstrap = (bootstrap.lower() == 'true') # Boolean
        # Money
        self.nodeNr = int(nodeNr)
        self.wallet = Wallet()
        # For consensus
        self.allBlockchains = {}
        self.currentBlock = None
        # IPs
        self.ipList = [(0, self.bootstrapAddr, self.wallet.get_addr())]
        self.id = 0
        self.nodesActive = 0
        # Buffer to store incoming transactions
        self.buffer = []
        # Blockchain
        self.blockchain = Blockchain()

        # Flag that indicates that we have all nodes
        self.nodeFlag = threading.Event()
        self.nodeFlag.clear()

        self.waitThread_ = threading.Thread(target=self.waitThread)
        self.waitThread_.start()

        minings.clear()

        if self.bootstrap:
            bootThread = threading.Thread(target=self.broadcastNodes)
            bootThread.start()
            tr = Transaction(self.wallet.get_addr(),
                             self.wallet.get_addr(), 100*(self.nodeNr+1), [], 0)
            tr.signature = self.wallet.sign(tr.tid)
            self.wallet.addTransaction(tr)
            genBlock = Block(0, [tr], 0, 1)
            self.blockchain.addBlock(genBlock)

        else:
            res = {'addrr': self.addr, 'pub_key': self.wallet.get_addr()}
            res = json.dumps(res)
            requests.post(self.bootstrapAddr + "/bootstrap_register", data=res,
                          headers={'Content-type': 'application/json', 'Accept': 'text/plain'})


    def addNode(self, IP, addr):
        self.ipList.append((self.nodesActive + 1, IP, addr))
        self.wallet.balances[addr] = 0
        self.nodesActive += 1
        if self.nodesActive >= self.nodeNr:
            self.nodeFlag.set()
        return True

    def setIPList(self, ipList):
        self.ipList = ipList
        self.wallet.setOutputs(self.ipList)
        self.id = self.getID(self.wallet.get_addr())
        print('My id:', self.id)
        return

    def getSK(self):
        return [i[2] for i in self.ipList]

    def setGenesis(self, block):
        genesisblock = json.loads(block)
        # print(genesisblock['transactions'])
        t = json.loads(genesisblock['transactions'][0])    # Load the transaction
        transaction = Transaction(
            t['sender'], t['receiver'], t['amount'], t['inputs'], t['amtLeft'], t['tid'], t['signature'].encode('ISO-8859-1'))
        current_block = Block(
            genesisblock['index'], [transaction], genesisblock['nonce'],
            genesisblock['previous_hash']
        )
        self.blockchain.addBlock(current_block)
        self.wallet.addTransaction(transaction)
        print('Initialized.')
        self.nodeFlag.set()

    def getBalance(self):
        return self.wallet.getMyBalance()

    def getBalanceOf(self, id):
        return self.wallet.getBalance(self.ipList[int(id)][2])

    def getAddr(self, id):
        return self.ipList[id][2]
    
    def getFullAddr(self):
        return self.ipList[self.id][1]
    
    def getID(self, addr):
        for i in self.ipList:
            if i[2] == addr:
                return i[0]
        print('Error: Not existant address.')
        return self.ipList[0][2]

    def createTransaction(self, receiverID, ammount):
        self.buffer.append([receiverID, None, ammount, None, None, None, None, True])

    def createTransaction1(self, receiverID, ammount):
        print("Creating transaction.")
        now = time.time()
        # Create transaction
        prev_tr, amt = self.wallet.getMoney(ammount)
        new_transaction = Transaction(self.getAddr(self.id), self.getAddr(receiverID), 
                                      ammount, prev_tr, amt-ammount)
        # Sign it
        new_transaction.signature = self.wallet.sign(new_transaction.tid)
        self.wallet.addTransaction(new_transaction)
        self.broadcastTransaction(new_transaction)
        now = time.time() - now
        print(f'Inserting transaction from {self.getID(new_transaction.sender)} to {self.getID(new_transaction.receiver)}.')
        self.blockchain.insert(new_transaction, self.ipList, self.id)

    def waitThread(self):
        ctr = 0
        self.nodeFlag.wait()
        while True:
            if minings.isSet():
                minings.wait()
            if len(self.buffer) != 0:
                print(ctr)
                ctr+=1
                print(f'Reading transaction from', end="")
                itm = self.buffer.pop(0)
                sender, receiver, amt, inputs, amtLeft, tid, signature, create = itm
                valLock.acquire()
                if not create:
                    tr = Transaction(sender, receiver, amt, inputs, amtLeft, tid, signature.encode('ISO-8859-1'))
                    print(f" {self.getID(sender)} -> {self.getID(receiver)}.")
                    # If invalid ignore block
                    if self.validateTransaction(tr) != 'Accepted.':
                        print(self.validateTransaction(tr))
                        continue
                    # Insert to block
                    self.blockchain.insert(tr, self.ipList, self.id)
                    self.wallet.addTransaction(tr)
                else:
                    self.createTransaction1(sender, amt)
                valLock.release()

    def broadcastNodes(self):
        self.nodeFlag.wait()
        print('All nodes joined, sharing IDs')
        time.sleep(2)
        # Broadcast Nodes to everyone
        ipList = {
            'ipList': self.ipList,
            'genBlock': self.blockchain.genBlock().convert_block()
        }
        ipList = json.dumps(ipList)
        # print('IP list:', ipList)
        for tup in self.ipList[1:]:
            requests.post(tup[1]+'/child_inform', data=ipList,
                          headers={'Content-type': 'application/json', 'Accept': 'text/plain'})

        time.sleep(2)
        for tup in self.ipList[1:]:
            self.createTransaction(tup[0], 100)
        return

    def broadcastTransaction(self, transaction):
        # Broadcast Transaction to everyone
        print("Broadcasting Transaction.")
        tmp = json.loads(transaction.toJSON())
        # print(tmp)
        for tup in self.ipList:
            if tup[0] != self.id:
                requests.post(tup[1] + "/broadcast", json=tmp, headers={
                              'Content-type': 'application/json', 'Accept': 'text/plain'})
        return

    def broadcastConsensus(self):
        print('We\'re consensing!')
        tmp = {'address': self.getFullAddr()}
        for tup in self.ipList:
            if tup[0] != self.id:
                requests.post(tup[1] + "/consensus", json=tmp, headers={
                              'Content-type': 'application/json', 'Accept': 'text/plain'})

    def validateTransaction(self, transaction):
        # Check signature
        if not transaction.verifySignature():
            return 'Signature verification failed.'
        if transaction.sender == transaction.receiver:
            return 'Sending yourself money is forbidden.'
        # Check money
        amt = self.wallet.getBalance(transaction.sender)
        if amt < transaction.amount:
            return 'Account balance too low.'
        if amt < 0:
            return 'Negative Coins.'
        return 'Accepted.'
    
    def validateBlock(self, block, creationTime):
        self.blockchain.stopMine.set()
        block = json.loads(block)
        newBlock = Block(0,[],0,0)
        newBlock.set(block)
        tmp = newBlock.hashing()
        if tmp != block['current_hash']:
            print('Invalid block with:')
            print(tmp)
            print(block['current_hash'])
            return False
        valLock.acquire()
        #print('hk;',newBlock.current_hash)
        #print('pk;',newBlock.previous_hash)
        #print('lk;',self.blockchain.getLastHash())
        print('Validating.')
        if not self.waitThread_.is_alive():
            print('Dead thread')
            self.waitThread_.start()
        print(len(self.buffer))
        if block['previous_hash'] != self.blockchain.getLastHash():
            self.currentBlock = newBlock
            self.broadcastConsensus()
            self.resolveConflict()
            print('Current length:',len(self.blockchain.blockchain))
            print('Validate chain',self.validateChain())
            self.blockchain.stopMine.clear()
            minings.clear()
            valLock.release()
            return True
        #bcLock.acquire()
        self.blockchain.blockchain.append(newBlock)
        #bcLock.release()
        print('Current length:',len(self.blockchain.blockchain))
        print('Validate chain',self.validateChain())
        self.blockchain.stopMine.clear()
        valLock.release()
        minings.clear()
        return True
    
    def resolveConflict(self):
        # Wait for all nodes to send their blockchains
        while len(self.allBlockchains) != self.nodeNr:
            continue
        newChain = max(self.allBlockchains.values(), key=len)
        # Reset dictionary
        self.allBlockchains = {}

        blocks = []
        for newBlock in newChain:
            b = json.loads(newBlock)
            block = Block(0,[],0,0)
            block.set(b)
            blocks.append(block)
        self.blockchain.blockchain = blocks
        return

    def validateChain(self):
        for i, bl in enumerate(self.blockchain.blockchain):
            if i==0:continue
            if bl.previous_hash != self.blockchain.blockchain[i-1].current_hash:
                return False
            if bl.current_hash != bl.hashing():
                return False
        return True

