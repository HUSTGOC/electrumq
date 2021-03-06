# -*- coding: utf-8 -*-
import sys

import struct
import types

from electrumq.utils import print_error
from electrumq.utils.base58 import hash160_to_p2pkh, hash160_to_p2sh, hash_160, \
    bc_address_to_type_and_hash_160, public_key_to_p2pkh
from electrumq.utils.key_store import xpubkey_to_address, xpubkey_to_pubkey
from electrumq.utils.parameter import TYPE_ADDRESS, TYPE_SCRIPT, TYPE_PUBKEY, Parameter
from electrumq.utils.parser import op_push

__author__ = 'zhouqi'

NO_SIGNATURE = 'ff'


class P2PKHScript(object):
    def get_signature_script(self):
        pass

    def get_pubkey_script(self, address):
        addrtype, hash_160 = bc_address_to_type_and_hash_160(address)
        if addrtype == Parameter().ADDRTYPE_P2PKH:
            script = '76a9'  # op_dup, op_hash_160
            script += push_script(hash_160.encode('hex'))
            script += '88ac'  # op_equalverify, op_checksig
        return script


class P2SHScript(object):
    def get_signature_script(self):
        pass

    def get_pubkey_script(self):
        pass

    def get_redeem_script(self, pubkey_list, n):
        return multisig_script(pubkey_list, n)


class Script(object):
    def get_script_pubkey(self, address):
        addrtype, hash_160 = bc_address_to_type_and_hash_160(address)
        if addrtype == Parameter().ADDRTYPE_P2PKH:
            script = '76a9'  # op_dup, op_hash_160
            script += push_script(hash_160.encode('hex'))
            script += '88ac'  # op_equalverify, op_checksig
        elif addrtype == Parameter().ADDRTYPE_P2SH:
            script = 'a9'  # op_hash_160
            script += push_script(hash_160.encode('hex'))
            script += '87'  # op_equal
        else:
            raise BaseException('unknown address type')
        return script

    def parse_scriptSig(self, bytes):
        d = {}
        try:
            decoded = [x for x in script_GetOp(bytes)]
        except Exception:
            # coinbase transactions raise an exception
            # print_error("cannot find address in input script", bytes.encode('hex'))
            return

        match = [opcodes.OP_PUSHDATA4]
        if self.match_decoded(decoded, match):
            item = decoded[0][1]
            if item[0] == chr(0):
                redeemScript = item.encode('hex')
                d['address'] = hash160_to_p2sh(hash_160(redeemScript.decode('hex')))
                d['type'] = 'p2wpkh-p2sh'
                d['redeemScript'] = redeemScript
                d['x_pubkeys'] = ["(witness)"]
                d['pubkeys'] = ["(witness)"]
                d['signatures'] = ['(witness)']
                d['num_sig'] = 1
            else:
                # payto_pubkey
                d['type'] = 'p2pk'
                d['address'] = "(pubkey)"
                d['signatures'] = [item.encode('hex')]
                d['num_sig'] = 1
                d['x_pubkeys'] = ["(pubkey)"]
                d['pubkeys'] = ["(pubkey)"]
            return

        # non-generated TxIn transactions push a signature
        # (seventy-something bytes) and then their public key
        # (65 bytes) onto the stack:
        match = [opcodes.OP_PUSHDATA4, opcodes.OP_PUSHDATA4]
        if self.match_decoded(decoded, match):
            sig = decoded[0][1].encode('hex')
            x_pubkey = decoded[1][1].encode('hex')
            try:
                signatures = parse_sig([sig])
                pubkey, address = xpubkey_to_address(x_pubkey)
            except:
                import traceback
                traceback.print_exc(file=sys.stdout)
                # print_error("cannot find address in input script", bytes.encode('hex'))
                return
            d['type'] = 'p2pkh'
            d['signatures'] = signatures
            d['x_pubkeys'] = [x_pubkey]
            d['num_sig'] = 1
            d['pubkeys'] = [pubkey]
            d['address'] = address
            return

        # p2sh transaction, m of n
        match = [opcodes.OP_0] + [opcodes.OP_PUSHDATA4] * (len(decoded) - 1)
        if not self.match_decoded(decoded, match):
            # print_error("cannot find address in input script", bytes.encode('hex'))
            return
        x_sig = [x[1].encode('hex') for x in decoded[1:-1]]
        dec2 = [x for x in script_GetOp(decoded[-1][1])]
        m = dec2[0][0] - opcodes.OP_1 + 1
        n = dec2[-2][0] - opcodes.OP_1 + 1
        op_m = opcodes.OP_1 + m - 1
        op_n = opcodes.OP_1 + n - 1
        match_multisig = [op_m] + [opcodes.OP_PUSHDATA4] * n + [op_n, opcodes.OP_CHECKMULTISIG]
        if not self.match_decoded(dec2, match_multisig):
            # print_error("cannot find address in input script", bytes.encode('hex'))
            return
        x_pubkeys = map(lambda x: x[1].encode('hex'), dec2[1:-2])
        pubkeys = [xpubkey_to_pubkey(x) for x in x_pubkeys]
        redeemScript = multisig_script(pubkeys, m)
        # write result in d
        d['type'] = 'p2sh'
        d['num_sig'] = m
        d['signatures'] = parse_sig(x_sig)
        d['x_pubkeys'] = x_pubkeys
        d['pubkeys'] = pubkeys
        d['redeemScript'] = redeemScript
        d['address'] = hash160_to_p2sh(hash_160(redeemScript.decode('hex')))

    def match_decoded(self, decoded, to_match):
        if len(decoded) != len(to_match):
            return False
        for i in range(len(decoded)):
            if to_match[i] == opcodes.OP_PUSHDATA4 and decoded[i][0] <= opcodes.OP_PUSHDATA4 and \
                            decoded[i][0] > 0:
                continue  # Opcodes below OP_PUSHDATA4 all just push data onto stack, and are equivalent.
            if to_match[i] != decoded[i][0]:
                return False
        return True

    def input_script(self, d, pubkeys, x_pubkeys, estimate_size=False):
        _type = d['type']
        if _type == 'coinbase':
            return d['scriptSig']
        pubkeys, sig_list = self.get_siglist(d, pubkeys, x_pubkeys, estimate_size)
        if len(sig_list) == 0:
            # no sig means not sig yet
            return ''
        script = ''.join(push_script(x) for x in sig_list)
        if _type == 'p2pk':
            pass
        elif _type == 'p2sh':
            # put op_0 before script
            script = '00' + script
            redeem_script = multisig_script(pubkeys, d['num_sig'])
            script += push_script(redeem_script)
        elif _type == 'p2pkh':
            script += push_script(pubkeys[0])
        elif _type == 'p2wpkh-p2sh':
            redeem_script = d.get('redeemScript') or segwit_script(pubkeys[0])
            return push_script(redeem_script)
        elif _type == 'address':
            script += push_script(pubkeys[0])
        else:
            raise TypeError('Unknown txin type', _type)
        return script

    def get_siglist(self, d, pubkeys, x_pubkeys, estimate_size=False):
        # if we have enough signatures, we use the actual pubkeys
        # otherwise, use extended pubkeys (with bip32 derivation)
        num_sig = d.get('num_sig', 1)
        if estimate_size:
            # we assume that signature will be 0x48 bytes long
            pk_list = ["00" * 0x21] * num_sig
            sig_list = ["00" * 0x48] * num_sig
        else:
            # pubkeys, x_pubkeys = self.get_sorted_pubkeys()
            x_signatures = d['signatures']
            signatures = filter(None, x_signatures)
            is_complete = len(signatures) == num_sig
            if is_complete:
                pk_list = pubkeys
                sig_list = [(sig + '01') for sig in signatures]
            else:
                pk_list = x_pubkeys
                sig_list = [(sig + '01') if sig else NO_SIGNATURE for sig in x_signatures]
        return pk_list, sig_list


class EnumException(Exception):
    pass


class Enumeration:
    def __init__(self, name, enumList):
        self.__doc__ = name
        lookup = {}
        reverseLookup = {}
        i = 0
        uniqueNames = []
        uniqueValues = []
        for x in enumList:
            if type(x) == types.TupleType:
                x, i = x
            if type(x) != types.StringType:
                raise EnumException, "enum name is not a string: " + x
            if type(i) != types.IntType:
                raise EnumException, "enum value is not an integer: " + i
            if x in uniqueNames:
                raise EnumException, "enum name is not unique: " + x
            if i in uniqueValues:
                raise EnumException, "enum value is not unique for " + x
            uniqueNames.append(x)
            uniqueValues.append(i)
            lookup[x] = i
            reverseLookup[i] = x
            i = i + 1
        self.lookup = lookup
        self.reverseLookup = reverseLookup

    def __getattr__(self, attr):
        if not self.lookup.has_key(attr):
            raise AttributeError
        return self.lookup[attr]

    def whatis(self, value):
        return self.reverseLookup[value]


opcodes = Enumeration("Opcodes", [
    ("OP_0", 0), ("OP_PUSHDATA1", 76), "OP_PUSHDATA2", "OP_PUSHDATA4", "OP_1NEGATE", "OP_RESERVED",
    "OP_1", "OP_2", "OP_3", "OP_4", "OP_5", "OP_6", "OP_7",
    "OP_8", "OP_9", "OP_10", "OP_11", "OP_12", "OP_13", "OP_14", "OP_15", "OP_16",
    "OP_NOP", "OP_VER", "OP_IF", "OP_NOTIF", "OP_VERIF", "OP_VERNOTIF", "OP_ELSE", "OP_ENDIF",
    "OP_VERIFY",
    "OP_RETURN", "OP_TOALTSTACK", "OP_FROMALTSTACK", "OP_2DROP", "OP_2DUP", "OP_3DUP", "OP_2OVER",
    "OP_2ROT", "OP_2SWAP",
    "OP_IFDUP", "OP_DEPTH", "OP_DROP", "OP_DUP", "OP_NIP", "OP_OVER", "OP_PICK", "OP_ROLL",
    "OP_ROT",
    "OP_SWAP", "OP_TUCK", "OP_CAT", "OP_SUBSTR", "OP_LEFT", "OP_RIGHT", "OP_SIZE", "OP_INVERT",
    "OP_AND",
    "OP_OR", "OP_XOR", "OP_EQUAL", "OP_EQUALVERIFY", "OP_RESERVED1", "OP_RESERVED2", "OP_1ADD",
    "OP_1SUB", "OP_2MUL",
    "OP_2DIV", "OP_NEGATE", "OP_ABS", "OP_NOT", "OP_0NOTEQUAL", "OP_ADD", "OP_SUB", "OP_MUL",
    "OP_DIV",
    "OP_MOD", "OP_LSHIFT", "OP_RSHIFT", "OP_BOOLAND", "OP_BOOLOR",
    "OP_NUMEQUAL", "OP_NUMEQUALVERIFY", "OP_NUMNOTEQUAL", "OP_LESSTHAN",
    "OP_GREATERTHAN", "OP_LESSTHANOREQUAL", "OP_GREATERTHANOREQUAL", "OP_MIN", "OP_MAX",
    "OP_WITHIN", "OP_RIPEMD160", "OP_SHA1", "OP_SHA256", "OP_HASH160",
    "OP_HASH256", "OP_CODESEPARATOR", "OP_CHECKSIG", "OP_CHECKSIGVERIFY", "OP_CHECKMULTISIG",
    "OP_CHECKMULTISIGVERIFY",
    ("OP_SINGLEBYTE_END", 0xF0),
    ("OP_DOUBLEBYTE_BEGIN", 0xF000),
    "OP_PUBKEY", "OP_PUBKEYHASH",
    ("OP_INVALIDOPCODE", 0xFFFF),
])


def script_GetOp(bytes):
    i = 0
    while i < len(bytes):
        vch = None
        opcode = ord(bytes[i])
        i += 1
        if opcode >= opcodes.OP_SINGLEBYTE_END:
            opcode <<= 8
            opcode |= ord(bytes[i])
            i += 1

        if opcode <= opcodes.OP_PUSHDATA4:
            nSize = opcode
            if opcode == opcodes.OP_PUSHDATA1:
                nSize = ord(bytes[i])
                i += 1
            elif opcode == opcodes.OP_PUSHDATA2:
                (nSize,) = struct.unpack_from('<H', bytes, i)
                i += 2
            elif opcode == opcodes.OP_PUSHDATA4:
                (nSize,) = struct.unpack_from('<I', bytes, i)
                i += 4
            vch = bytes[i:i + nSize]
            i += nSize

        yield (opcode, vch, i)


def script_GetOpName(opcode):
    return (opcodes.whatis(opcode)).replace("OP_", "")


def decode_script(bytes):
    result = ''
    for (opcode, vch, i) in script_GetOp(bytes):
        if len(result) > 0: result += " "
        if opcode <= opcodes.OP_PUSHDATA4:
            result += "%d:" % (opcode,)
            result += vch.encode('hex')
        else:
            result += script_GetOpName(opcode)
    return result


def match_decoded(decoded, to_match):
    if len(decoded) != len(to_match):
        return False
    for i in range(len(decoded)):
        if to_match[i] == opcodes.OP_PUSHDATA4 and decoded[i][0] <= opcodes.OP_PUSHDATA4 and \
                        decoded[i][0] > 0:
            continue  # Opcodes below OP_PUSHDATA4 all just push data onto stack, and are equivalent.
        if to_match[i] != decoded[i][0]:
            return False
    return True


def parse_sig(x_sig):
    s = []
    for sig in x_sig:
        if sig[-2:] == '01':
            s.append(sig[:-2])
        else:
            assert sig == NO_SIGNATURE
            s.append(None)
    return s


def parse_scriptSig(d, bytes):
    try:
        decoded = [x for x in script_GetOp(bytes)]
    except Exception:
        # coinbase transactions raise an exception
        print_error("cannot find address in input script", bytes.encode('hex'))
        return

    match = [opcodes.OP_PUSHDATA4]
    if match_decoded(decoded, match):
        item = decoded[0][1]
        if item[0] == chr(0):
            redeemScript = item.encode('hex')
            d['address'] = hash160_to_p2sh(hash_160(redeemScript.decode('hex')))
            d['type'] = 'p2wpkh-p2sh'
            d['redeemScript'] = redeemScript
            d['x_pubkeys'] = ["(witness)"]
            d['pubkeys'] = ["(witness)"]
            d['signatures'] = ['(witness)']
            d['num_sig'] = 1
        else:
            # payto_pubkey
            d['type'] = 'p2pk'
            d['address'] = "(pubkey)"
            d['signatures'] = [item.encode('hex')]
            d['num_sig'] = 1
            d['x_pubkeys'] = ["(pubkey)"]
            d['pubkeys'] = ["(pubkey)"]
        return

    # non-generated TxIn transactions push a signature
    # (seventy-something bytes) and then their public key
    # (65 bytes) onto the stack:
    match = [opcodes.OP_PUSHDATA4, opcodes.OP_PUSHDATA4]
    if match_decoded(decoded, match):
        sig = decoded[0][1].encode('hex')
        x_pubkey = decoded[1][1].encode('hex')
        try:
            signatures = parse_sig([sig])
            pubkey, address = xpubkey_to_address(x_pubkey)
        except:
            import traceback
            traceback.print_exc(file=sys.stdout)
            # print_error("cannot find address in input script", bytes.encode('hex'))
            return
        d['type'] = 'p2pkh'
        d['signatures'] = signatures
        d['x_pubkeys'] = [x_pubkey]
        d['num_sig'] = 1
        d['pubkeys'] = [pubkey]
        d['address'] = address
        return

    # p2sh transaction, m of n
    match = [opcodes.OP_0] + [opcodes.OP_PUSHDATA4] * (len(decoded) - 1)
    if not match_decoded(decoded, match):
        print_error("cannot find address in input script", bytes.encode('hex'))
        return
    x_sig = [x[1].encode('hex') for x in decoded[1:-1]]
    dec2 = [x for x in script_GetOp(decoded[-1][1])]
    m = dec2[0][0] - opcodes.OP_1 + 1
    n = dec2[-2][0] - opcodes.OP_1 + 1
    op_m = opcodes.OP_1 + m - 1
    op_n = opcodes.OP_1 + n - 1
    match_multisig = [op_m] + [opcodes.OP_PUSHDATA4] * n + [op_n, opcodes.OP_CHECKMULTISIG]
    if not match_decoded(dec2, match_multisig):
        print_error("cannot find address in input script", bytes.encode('hex'))
        return
    x_pubkeys = map(lambda x: x[1].encode('hex'), dec2[1:-2])
    pubkeys = [xpubkey_to_pubkey(x) for x in x_pubkeys]
    redeemScript = multisig_script(pubkeys, m)
    # write result in d
    d['type'] = 'p2sh'
    d['num_sig'] = m
    d['signatures'] = parse_sig(x_sig)
    d['x_pubkeys'] = x_pubkeys
    d['pubkeys'] = pubkeys
    d['redeemScript'] = redeemScript
    d['address'] = hash160_to_p2sh(hash_160(redeemScript.decode('hex')))


def parse_type_script_sig(bytes):
    decoded = [x for x in script_GetOp(bytes)]

    match = [opcodes.OP_PUSHDATA4]
    if match_decoded(decoded, match):
        item = decoded[0][1]
        if item[0] == chr(0):
            return 'p2wpkh-p2sh'
        else:
            return 'p2pk'
    match = [opcodes.OP_PUSHDATA4, opcodes.OP_PUSHDATA4]
    if match_decoded(decoded, match):
        return 'p2pkh'

    # p2sh transaction, m of n
    match = [opcodes.OP_0] + [opcodes.OP_PUSHDATA4] * (len(decoded) - 1)
    if not match_decoded(decoded, match):
        print_error("cannot find address in input script", bytes.encode('hex'))
        return
    x_sig = [x[1].encode('hex') for x in decoded[1:-1]]
    dec2 = [x for x in script_GetOp(decoded[-1][1])]
    m = dec2[0][0] - opcodes.OP_1 + 1
    n = dec2[-2][0] - opcodes.OP_1 + 1
    op_m = opcodes.OP_1 + m - 1
    op_n = opcodes.OP_1 + n - 1
    match_multisig = [op_m] + [opcodes.OP_PUSHDATA4] * n + [op_n, opcodes.OP_CHECKMULTISIG]
    if not match_decoded(dec2, match_multisig):
        print_error("cannot find address in input script", bytes.encode('hex'))
        return
    x_pubkeys = map(lambda x: x[1].encode('hex'), dec2[1:-2])
    pubkeys = [xpubkey_to_pubkey(x) for x in x_pubkeys]
    redeemScript = multisig_script(pubkeys, m)
    # write result in d
    return 'p2sh', hash160_to_p2sh(hash_160(redeemScript.decode('hex'))), redeemScript


def parse_script_sig(bytes):
    try:
        decoded = [x for x in script_GetOp(bytes)]
    except Exception:
        # coinbase transactions raise an exception
        print_error("cannot find address in input script", bytes.encode('hex'))
        return

    match = [opcodes.OP_PUSHDATA4]
    if match_decoded(decoded, match):
        item = decoded[0][1]
        if item[0] == chr(0):
            redeemScript = item.encode('hex')
            return 'p2wpkh-p2sh', hash160_to_p2sh(hash_160(redeemScript.decode('hex'))), None

        else:
            return 'p2pk', None, None

    # non-generated TxIn transactions push a signature
    # (seventy-something bytes) and then their public key
    # (65 bytes) onto the stack:
    match = [opcodes.OP_PUSHDATA4, opcodes.OP_PUSHDATA4]
    if match_decoded(decoded, match):
        sig = decoded[0][1].encode('hex')
        pubkey = decoded[1][1].encode('hex')
        address = public_key_to_p2pkh(pubkey.decode('hex'))
        return 'p2pkh', address, pubkey

    # p2sh transaction, m of n
    match = [opcodes.OP_0] + [opcodes.OP_PUSHDATA4] * (len(decoded) - 1)
    if not match_decoded(decoded, match):
        print_error("cannot find address in input script", bytes.encode('hex'))
        return
    x_sig = [x[1].encode('hex') for x in decoded[1:-1]]
    dec2 = [x for x in script_GetOp(decoded[-1][1])]
    m = dec2[0][0] - opcodes.OP_1 + 1
    n = dec2[-2][0] - opcodes.OP_1 + 1
    op_m = opcodes.OP_1 + m - 1
    op_n = opcodes.OP_1 + n - 1
    match_multisig = [op_m] + [opcodes.OP_PUSHDATA4] * n + [op_n, opcodes.OP_CHECKMULTISIG]
    if not match_decoded(dec2, match_multisig):
        print_error("cannot find address in input script", bytes.encode('hex'))
        return
    x_pubkeys = map(lambda x: x[1].encode('hex'), dec2[1:-2])
    pubkeys = [xpubkey_to_pubkey(x) for x in x_pubkeys]
    redeemScript = multisig_script(pubkeys, m)
    # write result in d
    return 'p2sh', hash160_to_p2sh(hash_160(redeemScript.decode('hex'))), redeemScript


def parse_script_pub_key(bytes):
    decoded = [x for x in script_GetOp(bytes)]

    # The Genesis Block, self-payments, and pay-by-IP-address payments look like:
    # 65 BYTES:... CHECKSIG
    match = [opcodes.OP_PUSHDATA4, opcodes.OP_CHECKSIG]
    if match_decoded(decoded, match):
        return 'p2pk', decoded[0][1].encode('hex')

    # Pay-by-Bitcoin-address TxOuts look like:
    # DUP HASH160 20 BYTES:... EQUALVERIFY CHECKSIG
    match = [opcodes.OP_DUP, opcodes.OP_HASH160, opcodes.OP_PUSHDATA4, opcodes.OP_EQUALVERIFY,
             opcodes.OP_CHECKSIG]
    if match_decoded(decoded, match):
        return 'p2pkh', hash160_to_p2pkh(decoded[2][1])

    # p2sh
    match = [opcodes.OP_HASH160, opcodes.OP_PUSHDATA4, opcodes.OP_EQUAL]
    if match_decoded(decoded, match):
        return 'p2sh', hash160_to_p2sh(decoded[1][1])

    return 'unknown', None


def get_address_from_output_script(bytes):
    decoded = [x for x in script_GetOp(bytes)]

    # The Genesis Block, self-payments, and pay-by-IP-address payments look like:
    # 65 BYTES:... CHECKSIG
    match = [opcodes.OP_PUSHDATA4, opcodes.OP_CHECKSIG]
    if match_decoded(decoded, match):
        return TYPE_PUBKEY, decoded[0][1].encode('hex')

    # Pay-by-Bitcoin-address TxOuts look like:
    # DUP HASH160 20 BYTES:... EQUALVERIFY CHECKSIG
    match = [opcodes.OP_DUP, opcodes.OP_HASH160, opcodes.OP_PUSHDATA4, opcodes.OP_EQUALVERIFY,
             opcodes.OP_CHECKSIG]
    if match_decoded(decoded, match):
        return TYPE_ADDRESS, hash160_to_p2pkh(decoded[2][1])

    # p2sh
    match = [opcodes.OP_HASH160, opcodes.OP_PUSHDATA4, opcodes.OP_EQUAL]
    if match_decoded(decoded, match):
        return TYPE_ADDRESS, hash160_to_p2sh(decoded[1][1])

    return TYPE_SCRIPT, bytes


def push_script(x):
    return op_push(len(x) / 2) + x


def get_scriptPubKey(addr):
    addrtype, hash_160 = bc_address_to_type_and_hash_160(addr)
    if addrtype == Parameter().ADDRTYPE_P2PKH:
        script = '76a9'  # op_dup, op_hash_160
        script += push_script(hash_160.encode('hex'))
        script += '88ac'  # op_equalverify, op_checksig
    elif addrtype == Parameter().ADDRTYPE_P2SH:
        script = 'a9'  # op_hash_160
        script += push_script(hash_160.encode('hex'))
        script += '87'  # op_equal
    else:
        raise BaseException('unknown address type')
    return script


def segwit_script(pubkey):
    pkh = hash_160(pubkey.decode('hex')).encode('hex')
    return '00' + push_script(pkh)


def multisig_script(public_keys, m):
    n = len(public_keys)
    assert n <= 15
    assert m <= n
    op_m = format(opcodes.OP_1 + m - 1, 'x')
    op_n = format(opcodes.OP_1 + n - 1, 'x')
    keylist = [op_push(len(k) / 2) + k for k in public_keys]
    return op_m + ''.join(keylist) + op_n + 'ae'
