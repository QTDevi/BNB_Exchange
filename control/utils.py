from web3 import Web3
from web3.exceptions import ContractLogicError, BadFunctionCallOutput
import requests
import json
from datetime import datetime, timezone
from django.conf import settings
from decouple import config

# Connecting to one of the BSC Main-nets statically (Legacy)
# bsc = 'https://bsc-dataseed.bnbchain.org/'
# web3 = Web3(Web3.HTTPProvider(bsc))

# connecting to a websocket
web3 = Web3(Web3.HTTPProvider(settings.BSC_WS))


def fetch_abi(address, api_key):
    """
    Uses BSC API to fetch abi of the contract, and returns loaded json file
    :param address:
    :param api_key:
    :return: abi.json file
    """
    try:
        if not address.startswith("0x") or len(address) != 42:
            raise ValueError("Invalid contract address format.")

        url = "https://api.bscscan.com/api"
        params = {
            "module": "contract",
            "action": "getabi",
            "address": address,
            "apikey": api_key
        }

        response = requests.get(url, params=params, timeout=10)
        data = response.json()

        if response.status_code != 200:
            return {"error": f"HTTP Error {response.status_code}"}
        if "status" in data and data["status"] == "0":
            return {"error": f"API Error: {data.get('message', 'Unknown error')}"}

        abi = data["result"]
        if isinstance(abi, str):
            abi = json.loads(abi)
        return {"abi": sanitize_abi(abi)}

    except ValueError as ve:
        return {"error": f"ValueError: {str(ve)}"}

    except requests.exceptions.ConnectionError:
        return {"error": "Network error: Unable to connect to the BscScan API."}

    except requests.exceptions.Timeout:
        return {"error": "Request timed out. The API might be slow or down."}

    except requests.exceptions.RequestException as re:
        return {"error": f"RequestException: {str(re)}"}

    except Exception as e:
        if isinstance(e, list):
            return {"error": " ".join(str(i) for i in e)}
        return {"error": f"Unexpected error: {str(e)}"}


def fetch_tx(address, api_key, tx_type=None):
    """
    Fetch 5 last transactions for token/user
    :param address:
    :param api_key:
    :param tx_type:
    :return: transaction
    """
    try:
        if not address.startswith("0x") or len(address) != 42:
            raise ValueError("Invalid wallet address format.")
        url = "https://api.bscscan.com/api"
        if tx_type == "account":
            params = {
                "module": "account",
                "action": "txlist",
                "address": address,
                "startblock": 0,
                "endblock": 99999999,
                "sort": "desc",
                "apikey": api_key,
            }
        else:
            params = {
                "module": "account",
                "action": "tokentx",
                "address": address,
                "startblock": 0,
                "endblock": 99999999,
                "sort": "desc",
                "apikey": api_key,
            }
        response = requests.get(url, params, timeout=10)
        data = response.json()

        if response.status_code != 200:
            return {"error": f"HTTP Error {response.status_code}"}

        if "status" in data and data["status"] == "0":
            return {"error": f"API Error: {data.get('message', 'Unknown error')}"}

        return {"transactions": data["result"][:5]}

    except ValueError as ve:
        return {"error": f"ValueError: {str(ve)}"}

    except requests.exceptions.ConnectionError:
        return {"error": "Network error: Unable to connect to BscScan API."}

    except requests.exceptions.Timeout:
        return {"error": "Request timed out. The API might be slow or down."}

    except requests.exceptions.RequestException as re:
        return {"error": f"RequestException: {str(re)}"}

    except Exception as e:
        if isinstance(e, list):
            return {"error": " ".join(str(i) for i in e)}
        return {"error": f"Unexpected error: {str(e)}"}


def token_data(token, pair_contract):
    """
    connects pair contract to WBNB and returns token data
    :param token:
    :param pair_contract:
    :return: dictionary of price and reserves.
    """
    try:
        reserve = pair_contract.functions.getReserves().call()
        if not reserve or len(reserve) < 2:
            raise ValueError("Invalid reserves data from contract.")

        token_reserves = reserve[0]
        wbnb_reserves = reserve[1]
        if token_reserves == 0:
            raise ZeroDivisionError("Token reserves are zero, cannot calculate price.")

        price = wbnb_reserves / token_reserves
        api_key = config('API_KEY_BSCScan', cast=str)

        return {
            "price": price,
            "wbnb": wbnb_reserves,
            "token": token_reserves,
        }

    except ZeroDivisionError as ze:
        return {"error": f"ZeroDivisionError: {str(ze)}"}

    except ValueError as ve:
        return {"error": f"ValueError: {str(ve)}"}

    except ContractLogicError:
        return {"error": "ContractLogicError: Unable to fetch reserves. Possible invalid contract address."}

    except Exception as e:
        if isinstance(e, list):
            return {"error": " ".join(str(i) for i in e)}
        return {"error": f"Unexpected error: {str(e)}"}


def get_user_data(address):
    """
    Retrieves user data such as balance and transactions in one form
    :param address:
    :return:
    """
    try:
        if not address.startswith("0x") or len(address) != 42:
            raise ValueError("Invalid wallet address format.")
        balance = web3.from_wei(web3.eth.get_balance(address), 'ether')
        api_key = config('API_KEY_BSCScan', cast=str)
        tx = fetch_tx(address, api_key, "account")
        return {"balance": balance, "transactions": tx}

    except ValueError as ve:
        return {"error": f"ValueError: {str(ve)}"}

    except BadFunctionCallOutput:
        return {"error": "Web3 error: Unable to fetch balance. Possible RPC issue."}

    except Exception as e:
        if isinstance(e, list):
            return {"error": " ".join(str(i) for i in e)}
        return {"error": f"Unexpected error: {str(e)}"}


def get_transaction_info(tx_hash):
    """
    Specialised function on retrieving transaction info from web3.
    Information such as users, where, to whom, gas and other crucial information.
    :param tx_hash:
    :return: dictionary of values: to, from, value, gas and black number
    """
    try:
        if not tx_hash.startswith('0x'):
            return {"error": "Invalid transaction hash format"}

        tx = web3.eth.get_transaction(tx_hash)
        if not tx:
            return {"error": "Transaction not found"}

        receipt = web3.eth.get_transaction_receipt(tx_hash)
        if not receipt:
            return {"error": "Transaction receipt not found"}

        block = web3.eth.get_block(tx['blockNumber'])
        return {
            "transaction_hash": tx_hash,
            "from": tx["from"],
            "to": tx["to"],
            "value": web3.from_wei(tx["value"], "ether"),
            "gas_price": web3.from_wei(tx["gasPrice"], "gwei"),
            "block_number": tx["blockNumber"],
            "status": "Success" if receipt["status"] == 1 else "Failed",
            "gas_used": receipt["gasUsed"],
            "block_hash": receipt["blockHash"].hex(),
            "transaction_time": datetime.fromtimestamp(
                block['timestamp'],
                timezone.utc
            ).strftime('%Y-%m-%d %H:%M:%S'),
        }

    except Exception as e:
        return {"error": str(e)}


def fetch_and_use_abi(contract_address, api_key):
    """
    Standardise function to use abi after sanitization to avoid unnecessary arguments.
    :param contract_address:
    :param api_key:
    :return: Contract object
    """
    url = f'https://api.bscscan.com/api?module=contract&action=getabi&address={contract_address}&apikey={api_key}'
    response = requests.get(url)
    data = response.json()

    if data['status'] == '1':
        abi = data['result']

        if isinstance(abi, str):
            abi = json.loads(abi)

        sanitized_abi = sanitize_abi(abi)
        return sanitized_abi
    else:
        raise Exception(f"Error fetching ABI: {data.get('message', 'Unknown error')}")


def sanitize_abi(abi):
    """
    Sanitization function reducing unnecessary or none standard functions
    :param abi:
    :return: ABI of the contract
    """
    sanitized_abi = []
    for item in abi:
        if isinstance(item, dict):
            cleaned_item = {key: value for key, value in item.items() if key in ['type', 'inputs', 'name', 'outputs', 'payable', 'stateMutability']}
            sanitized_abi.append(cleaned_item)
        else:
            print(f"Skipping invalid ABI item: {item}")
    return sanitized_abi


def get_contract_instance(address, abi):
    """
    Get contract object from web3, function made for clarity when maintaining
    :param address:
    :param abi:
    :return: contract object
    """
    return web3.eth.contract(address=address, abi=abi)

