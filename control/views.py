from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.core.cache import cache
from django.conf import settings
from .utils import (
    get_user_data,
    fetch_and_use_abi,
    token_data,
    get_transaction_info,
    get_contract_instance
)
from web3 import Web3
from web3.exceptions import ContractLogicError
from django.urls import reverse
import re
from urllib.parse import quote, unquote
from decouple import config
from web3.middleware import ExtraDataToPOAMiddleware
from functools import wraps
import logging

# Set up logging
logger = logging.getLogger(__name__)

# Initialize Web3
web3 = Web3(Web3.HTTPProvider(settings.BSC_WS))
web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

# Constants and cache for 15 seconds
ADDRESS_REGEX = re.compile(r"^0x[a-fA-F0-9]{40}$")
TX_HASH_REGEX = re.compile(r"^0x[a-fA-F0-9]{64}$")
CACHE_TIMEOUT = 15
TOKEN_CACHE_PREFIX = 'token_data_'
ABI_CACHE_PREFIX = 'abi_'


# PancakeSwap setup
factory_address = '0xcA143Ce32Fe78f1f7019d7d551a6402fC5350c73'
wbnb_contract = '0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c'


# Main error handling
def handle_exceptions(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        try:
            return view_func(request, *args, **kwargs)
        except ContractLogicError as e:
            logger.error(f"Contract error in {view_func.__name__}: {str(e)}")
            return redirect(reverse("error", kwargs={
                "error_number": 500,
                "error_message": quote("Smart contract interaction failed.")
            }))
        except Exception as e:
            logger.error(f"Unexpected error in {view_func.__name__}: {str(e)}")
            return redirect(reverse("error", kwargs={
                "error_number": 500,
                "error_message": quote(str(e))
            }))

    return wrapper


# Returns and renders homepage
@handle_exceptions
def view_home(request):
    return render(request, 'home.html')


# checks address, redirects to errors as well as caches information with time out for 60 seconds.
@handle_exceptions
def view_token(request, address):
    if not ADDRESS_REGEX.match(address):
        return redirect(reverse("error", kwargs={
            "error_number": 400,
            "error_message": quote("Invalid token address format.")
        }))

    cache_key = f'{TOKEN_CACHE_PREFIX}{address}'
    cached_data = cache.get(cache_key)
    if cached_data:
        cached_data['address'] = address  # Ensure address is always in context
        return render(request, "token.html", cached_data)

    try:
        api_key = config("API_KEY_BSCScan", cast=str)

        # Cache factory ABI to reduce API calls
        factory_abi_key = f'{ABI_CACHE_PREFIX}factory'
        factory_abi = cache.get(factory_abi_key)
        if not factory_abi:
            factory_abi = fetch_and_use_abi(factory_address, api_key)
            cache.set(factory_abi_key, factory_abi, CACHE_TIMEOUT * 60)  # Cache for longer

        factory_contract = get_contract_instance(factory_address, factory_abi)
        pair_address = factory_contract.functions.getPair(address, wbnb_contract).call()

        if pair_address == "0x0000000000000000000000000000000000000000":
            return redirect(reverse("error", kwargs={
                "error_number": 404,
                "error_message": quote("No liquidity pool found for this token.")
            }))

        # Cache pair ABI
        pair_abi_key = f'{ABI_CACHE_PREFIX}{pair_address}'
        pair_abi = cache.get(pair_abi_key)
        if not pair_abi:
            pair_abi = fetch_and_use_abi(pair_address, api_key)
            cache.set(pair_abi_key, pair_abi, CACHE_TIMEOUT * 60)  # Cache for longer

        pair_contract = web3.eth.contract(address=pair_address, abi=pair_abi)
        token_info = token_data(address, pair_contract)

        if "error" in token_info:
            return redirect(reverse("error", kwargs={
                "error_number": 500,
                "error_message": quote(str(token_info["error"]))
            }))

        context = {
            "address": address,
            "price": token_info["price"],
            "wbnb": token_info["wbnb"],
            "token": token_info["token"],
        }

        cache.set(cache_key, context, CACHE_TIMEOUT)
        return render(request, "token.html", context)

    except Exception as e:
        logger.error(f"Error in view_token for address {address}: {str(e)}")
        return redirect(reverse("error", kwargs={
            "error_number": 500,
            "error_message": quote(f"Failed to fetch token data: {str(e)}")
        }))


# Use cache and handle get requests.
@require_http_methods(["GET"])
@handle_exceptions
def api_token_price(request, address):
    try:
        api_key = config("API_KEY_BSCScan", cast=str)

        # Use cached factory ABI if available
        factory_abi_key = f'{ABI_CACHE_PREFIX}factory'
        factory_abi = cache.get(factory_abi_key)
        if not factory_abi:
            factory_abi = fetch_and_use_abi(factory_address, api_key)
            cache.set(factory_abi_key, factory_abi, CACHE_TIMEOUT * 60)

        factory_contract = get_contract_instance(factory_address, factory_abi)
        pair_address = factory_contract.functions.getPair(address, wbnb_contract).call()

        if pair_address == "0x0000000000000000000000000000000000000000":
            return JsonResponse({
                "success": False,
                "error": "No liquidity pool found for this token."
            }, status=404)

        # Use cached pair ABI if available
        pair_abi_key = f'{ABI_CACHE_PREFIX}{pair_address}'
        pair_abi = cache.get(pair_abi_key)
        if not pair_abi:
            pair_abi = fetch_and_use_abi(pair_address, api_key)
            cache.set(pair_abi_key, pair_abi, CACHE_TIMEOUT * 60)

        pair_contract = web3.eth.contract(address=pair_address, abi=pair_abi)
        token_info = token_data(address, pair_contract)

        if "error" in token_info:
            return JsonResponse({
                "success": False,
                "error": str(token_info["error"])
            }, status=500)

        # Update the cache with new data
        cache_key = f'{TOKEN_CACHE_PREFIX}{address}'
        cache.set(cache_key, {
            "address": address,
            "price": token_info["price"],
            "wbnb": token_info["wbnb"],
            "token": token_info["token"],
        }, CACHE_TIMEOUT)

        return JsonResponse({
            "success": True,
            "price": token_info["price"],
            "wbnb": token_info["wbnb"],
            "token": token_info["token"]
        })

    except Exception as e:
        logger.error(f"Error refreshing token price for {address}: {str(e)}")
        return JsonResponse({
            "success": False,
            "error": str(e)
        }, status=500)


# Uses API and web3 requests to show last transactions and balance
@handle_exceptions
def view_user(request, address):
    if not ADDRESS_REGEX.match(address):
        return redirect(reverse("error", kwargs={
            "error_number": 400,
            "error_message": quote("Invalid wallet address format.")
        }))

    cache_key = f'user_data_{address}'
    cached_data = cache.get(cache_key)
    if cached_data:
        return render(request, "user.html", cached_data)

    try:
        user_data = get_user_data(address)
        if "error" in user_data:
            return redirect(reverse("error", kwargs={
                "error_number": 500,
                "error_message": quote(str(user_data["error"]))
            }))

        # Ensure transactions is always a list
        transactions = user_data["transactions"].get("transactions", [])
        if not isinstance(transactions, list):
            transactions = []

        context = {
            "address": address,
            "balance": user_data["balance"],
            "transactions": transactions
        }

        cache.set(cache_key, context, CACHE_TIMEOUT)
        return render(request, "user.html", context)

    except Exception as e:
        logger.error(f"Error in view_user for address {address}: {str(e)}")
        return redirect(reverse("error", kwargs={
            "error_number": 500,
            "error_message": quote(f"Failed to fetch user data: {str(e)}")
        }))

# Legacy code, unfinished yet
# Takes transaction hash to display its information with gas, price, value, where, to whom, etc.
@handle_exceptions
def view_tx(request, hash_tx):
    if not TX_HASH_REGEX.match(hash_tx):
        return redirect(reverse("error", kwargs={
            "error_number": 400,
            "error_message": quote("Invalid transaction hash format")
        }))

    cache_key = f'tx_data_{hash_tx}'
    cached_data = cache.get(cache_key)
    if cached_data:
        return render(request, "transaction.html", {"transaction": cached_data})

    data = get_transaction_info(hash_tx)
    if "error" in data:
        return redirect(reverse("error", kwargs={
            "error_number": 500,
            "error_message": quote("Failed to fetch transaction details")
        }))

    cache.set(cache_key, data, CACHE_TIMEOUT)
    return render(request, "transaction.html", {"transaction": data})


# Error displaying page with explanation about the error with the number
@handle_exceptions
def view_error(request, error_number, error_message):
    decoded_message = unquote(error_message)
    return render(request, "error.html", {
        "error_number": error_number,
        "error_message": decoded_message,
    })


# Main searching and redirecting logic. Prematurely checks the address and informs if it is wrong
@handle_exceptions
@handle_exceptions
def search_view(request, search_type):
    q = request.GET.get("q", "").strip()
    if not q:
        return redirect(reverse("error", kwargs={
            "error_number": 400,
            "error_message": quote("Input cannot be empty.")
        }))

    if search_type in ["token", "user"]:
        if not ADDRESS_REGEX.match(q):
            return redirect(reverse("error", kwargs={
                "error_number": 400,
                "error_message": quote("Invalid BSC address format.")
            }))
        return redirect(reverse(search_type, kwargs={"address": q}))
    elif search_type == "transaction":
        if not TX_HASH_REGEX.match(q):
            return redirect(reverse("error", kwargs={
                "error_number": 400,
                "error_message": quote("Invalid transaction hash format.")
            }))
        return redirect(reverse(search_type, kwargs={"hash_tx": q}))

    return redirect(reverse("error", kwargs={
        "error_number": 404,
        "error_message": quote("Invalid search type.")
    }))
