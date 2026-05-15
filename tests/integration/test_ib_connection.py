"""Integration test to verify connection to IB Gateway running in Docker."""

import os
import pytest
import asyncio
import structlog
from ibkr_mcp_service.services.ibkr_client import IBKRClient
from ibkr_mcp_service.config import Settings
from ibkr_mcp_service.models.domain import QuoteRequest, SecType, BarSize, WhatToShow

log = structlog.get_logger(__name__)

@pytest.mark.asyncio
async def test_ib_gateway_docker_connection():
    """
    Test connection to the IB Gateway container.
    By default, docker-compose maps 4001:4003.
    """
    test_settings = Settings(
        ibkr_host="127.0.0.1",
        ibkr_port=4002,  # Mapped from 4004 in docker-compose
        ibkr_client_id=99
    )
    
    client = IBKRClient()
    client._settings = test_settings
    
    # Give it a few retries as Docker might still be booting the IB Gateway
    max_retries = 5
    connected = False
    for i in range(max_retries):
        try:
            print(f"Connection attempt {i+1}/{max_retries}...")
            await client.connect()
            if client._ib.isConnected():
                connected = True
                break
        except Exception as e:
            print(f"Attempt {i+1} failed: {e}")
            await asyncio.sleep(5)
            
    assert connected, "Failed to connect to IB Gateway after multiple retries"
    
    try:
        server_version = client._ib.client.serverVersion()
        assert server_version > 0
        print(f"Connected! Server version: {server_version}")
        
        # Now fetch AAPL quote (last daily bar)
        print("Fetching AAPL quote...")
        contract = client.make_contract("AAPL", "STK")
        bars = await client.get_historical_data(
            contract=contract,
            duration_str="1 D",
            bar_size_setting="1 day",
            what_to_show="TRADES",
            use_rth=True,
            end_datetime=""
        )
        
        assert len(bars) > 0, "Should have received at least one bar for AAPL"
        last_bar = bars[-1]
        print(f"AAPL Last Quote (Daily Bar): Date={last_bar.date}, Close={last_bar.close}, Volume={last_bar.volume}")
        
    finally:
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(test_ib_gateway_docker_connection())
