"""
Plaid API service for managing bank connections and fetching investment data.
"""

import plaid
from plaid.api import plaid_api
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.investments_holdings_get_request import InvestmentsHoldingsGetRequest
from plaid.model.investments_transactions_get_request import InvestmentsTransactionsGetRequest
from plaid.model.investments_refresh_request import InvestmentsRefreshRequest
from plaid.model.accounts_get_request import AccountsGetRequest
from plaid.model.item_get_request import ItemGetRequest
from plaid.model.item_remove_request import ItemRemoveRequest
from plaid.model.products import Products
from plaid.model.country_code import CountryCode

from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
import logging

from app.core.config import settings
from app.modules.plaid.models import PlaidItem, PlaidAccount, PlaidInvestmentTransaction, PlaidHolding

logger = logging.getLogger(__name__)


class PlaidService:
    """Service for interacting with the Plaid API."""
    
    def __init__(self):
        """Initialize Plaid client based on environment settings."""
        if not settings.PLAID_CLIENT_ID or not settings.PLAID_SECRET:
            raise ValueError("Plaid credentials not configured. Set PLAID_CLIENT_ID and PLAID_SECRET in .env")
        
        # Determine Plaid environment
        # Note: Plaid SDK only has Sandbox and Production. "development" is mapped to Sandbox.
        env_map = {
            "sandbox": plaid.Environment.Sandbox,
            "development": plaid.Environment.Sandbox,  # Development uses Sandbox
            "production": plaid.Environment.Production,
        }
        plaid_env = env_map.get(settings.PLAID_ENV.lower(), plaid.Environment.Sandbox)
        
        configuration = plaid.Configuration(
            host=plaid_env,
            api_key={
                "clientId": settings.PLAID_CLIENT_ID,
                "secret": settings.PLAID_SECRET,
            }
        )
        
        api_client = plaid.ApiClient(configuration)
        self.client = plaid_api.PlaidApi(api_client)
        logger.info(f"Plaid client initialized for environment: {settings.PLAID_ENV}")
    
    def create_link_token(self, user_id: str = "agrawal_family") -> Dict[str, Any]:
        """
        Create a link token for Plaid Link initialization.
        
        Args:
            user_id: Unique identifier for the user
            
        Returns:
            Dict containing link_token and expiration
        """
        request = LinkTokenCreateRequest(
            user=LinkTokenCreateRequestUser(client_user_id=user_id),
            client_name="Agrawal Estate Planner",
            products=[Products("investments"), Products("transactions")],
            country_codes=[CountryCode("US")],
            language="en",
            # redirect_uri="http://localhost:3000/plaid-callback",  # Required for OAuth
        )
        
        response = self.client.link_token_create(request)
        
        return {
            "link_token": response.link_token,
            "expiration": response.expiration,
        }
    
    def exchange_public_token(self, public_token: str, db: Session) -> PlaidItem:
        """
        Exchange a public token for an access token and store the item.
        
        Args:
            public_token: Public token from Plaid Link
            db: Database session
            
        Returns:
            Created PlaidItem
        """
        # Exchange public token for access token
        exchange_request = ItemPublicTokenExchangeRequest(public_token=public_token)
        exchange_response = self.client.item_public_token_exchange(exchange_request)
        
        access_token = exchange_response.access_token
        item_id = exchange_response.item_id
        
        # Get item info (institution details)
        item_request = ItemGetRequest(access_token=access_token)
        item_response = self.client.item_get(item_request)
        item_info = item_response.item
        
        # Get institution name
        institution_name = None
        if item_info.institution_id:
            try:
                from plaid.model.institutions_get_by_id_request import InstitutionsGetByIdRequest
                inst_request = InstitutionsGetByIdRequest(
                    institution_id=item_info.institution_id,
                    country_codes=[CountryCode("US")]
                )
                inst_response = self.client.institutions_get_by_id(inst_request)
                institution_name = inst_response.institution.name
            except Exception as e:
                logger.warning(f"Could not fetch institution name: {e}")
        
        # Check if item already exists
        existing_item = db.query(PlaidItem).filter(PlaidItem.item_id == item_id).first()
        if existing_item:
            # Update existing item
            existing_item.access_token = access_token
            existing_item.is_active = True
            existing_item.error_code = None
            existing_item.error_message = None
            existing_item.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(existing_item)
            plaid_item = existing_item
        else:
            # Create new item
            plaid_item = PlaidItem(
                item_id=item_id,
                access_token=access_token,
                institution_id=item_info.institution_id,
                institution_name=institution_name,
            )
            db.add(plaid_item)
            db.commit()
            db.refresh(plaid_item)
        
        # Fetch and store accounts
        self._sync_accounts(plaid_item, db)
        
        return plaid_item
    
    def _sync_accounts(self, plaid_item: PlaidItem, db: Session) -> List[PlaidAccount]:
        """Sync accounts for a Plaid item."""
        accounts_request = AccountsGetRequest(access_token=plaid_item.access_token)
        accounts_response = self.client.accounts_get(accounts_request)
        
        synced_accounts = []
        for account in accounts_response.accounts:
            # Check if account exists
            existing = db.query(PlaidAccount).filter(
                PlaidAccount.account_id == account.account_id
            ).first()
            
            if existing:
                # Update existing
                existing.name = account.name
                existing.official_name = account.official_name
                existing.current_balance = str(account.balances.current) if account.balances.current else None
                existing.available_balance = str(account.balances.available) if account.balances.available else None
                existing.updated_at = datetime.utcnow()
                synced_accounts.append(existing)
            else:
                # Create new
                new_account = PlaidAccount(
                    item_id=plaid_item.id,
                    account_id=account.account_id,
                    name=account.name,
                    official_name=account.official_name,
                    type=account.type.value if account.type else "unknown",
                    subtype=account.subtype.value if account.subtype else None,
                    mask=account.mask,
                    current_balance=str(account.balances.current) if account.balances.current else None,
                    available_balance=str(account.balances.available) if account.balances.available else None,
                    iso_currency_code=account.balances.iso_currency_code or "USD",
                )
                db.add(new_account)
                synced_accounts.append(new_account)
        
        db.commit()
        return synced_accounts
    
    def get_investment_holdings(self, access_token: str) -> Dict[str, Any]:
        """
        Get current investment holdings for an item.
        
        Args:
            access_token: Plaid access token
            
        Returns:
            Dict with accounts, holdings, and securities
        """
        request = InvestmentsHoldingsGetRequest(access_token=access_token)
        response = self.client.investments_holdings_get(request)
        
        # Build securities lookup
        securities_map = {s.security_id: s for s in response.securities}
        
        holdings_data = []
        for holding in response.holdings:
            security = securities_map.get(holding.security_id)
            
            holding_info = {
                "account_id": holding.account_id,
                "security_id": holding.security_id,
                "quantity": float(holding.quantity) if holding.quantity else 0,
                "cost_basis": float(holding.cost_basis) if holding.cost_basis else None,
                "institution_price": float(holding.institution_price) if holding.institution_price else None,
                "institution_value": float(holding.institution_value) if holding.institution_value else None,
            }
            
            if security:
                holding_info.update({
                    "ticker_symbol": security.ticker_symbol,
                    "name": security.name,
                    "type": security.type,
                    # Option details
                    "option_type": getattr(security, "option_contract", {}).get("contract_type") if hasattr(security, "option_contract") and security.option_contract else None,
                    "strike_price": getattr(security, "option_contract", {}).get("strike_price") if hasattr(security, "option_contract") and security.option_contract else None,
                    "expiration_date": getattr(security, "option_contract", {}).get("expiration_date") if hasattr(security, "option_contract") and security.option_contract else None,
                    "underlying_security_ticker": getattr(security, "option_contract", {}).get("underlying_security_ticker") if hasattr(security, "option_contract") and security.option_contract else None,
                })
            
            holdings_data.append(holding_info)
        
        return {
            "accounts": [{"account_id": a.account_id, "name": a.name, "type": a.type.value} for a in response.accounts],
            "holdings": holdings_data,
            "securities_count": len(response.securities),
        }
    
    def get_investment_transactions(
        self, 
        access_token: str, 
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Get investment transactions for an item.
        
        Args:
            access_token: Plaid access token
            start_date: Start of date range (default: 30 days ago)
            end_date: End of date range (default: today)
            
        Returns:
            Dict with transactions and securities
        """
        if not start_date:
            start_date = datetime.now() - timedelta(days=30)
        if not end_date:
            end_date = datetime.now()
        
        request = InvestmentsTransactionsGetRequest(
            access_token=access_token,
            start_date=start_date.date(),
            end_date=end_date.date(),
        )
        response = self.client.investments_transactions_get(request)
        
        # Build securities lookup
        securities_map = {s.security_id: s for s in response.securities}
        
        transactions_data = []
        for txn in response.investment_transactions:
            security = securities_map.get(txn.security_id) if txn.security_id else None
            
            txn_info = {
                "investment_transaction_id": txn.investment_transaction_id,
                "account_id": txn.account_id,
                "date": str(txn.date),
                "name": txn.name,
                "type": txn.type.value if txn.type else None,
                "subtype": txn.subtype.value if txn.subtype else None,
                "quantity": float(txn.quantity) if txn.quantity else None,
                "price": float(txn.price) if txn.price else None,
                "amount": float(txn.amount) if txn.amount else None,
                "fees": float(txn.fees) if txn.fees else None,
            }
            
            if security:
                txn_info.update({
                    "ticker_symbol": security.ticker_symbol,
                    "security_name": security.name,
                    "security_type": security.type,
                })
                
                # Check for option contract
                if hasattr(security, "option_contract") and security.option_contract:
                    opt = security.option_contract
                    txn_info.update({
                        "option_type": opt.contract_type if hasattr(opt, "contract_type") else None,
                        "strike_price": float(opt.strike_price) if hasattr(opt, "strike_price") and opt.strike_price else None,
                        "expiration_date": str(opt.expiration_date) if hasattr(opt, "expiration_date") and opt.expiration_date else None,
                        "underlying_symbol": opt.underlying_security_ticker if hasattr(opt, "underlying_security_ticker") else None,
                    })
            
            transactions_data.append(txn_info)
        
        return {
            "transactions": transactions_data,
            "total_transactions": response.total_investment_transactions,
            "accounts": [a.account_id for a in response.accounts],
        }
    
    def refresh_investments(self, access_token: str) -> bool:
        """
        Request a refresh of investment data.
        
        Args:
            access_token: Plaid access token
            
        Returns:
            True if refresh was initiated
        """
        try:
            request = InvestmentsRefreshRequest(access_token=access_token)
            self.client.investments_refresh(request)
            return True
        except Exception as e:
            logger.error(f"Failed to refresh investments: {e}")
            return False
    
    def sync_transactions_to_db(
        self, 
        plaid_item: PlaidItem, 
        db: Session,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> int:
        """
        Fetch and store investment transactions to database.
        
        Args:
            plaid_item: PlaidItem to sync
            db: Database session
            start_date: Start date (default: 30 days ago)
            end_date: End date (default: today)
            
        Returns:
            Number of new transactions stored
        """
        data = self.get_investment_transactions(
            plaid_item.access_token,
            start_date,
            end_date
        )
        
        new_count = 0
        for txn in data["transactions"]:
            # Check if transaction already exists
            existing = db.query(PlaidInvestmentTransaction).filter(
                PlaidInvestmentTransaction.investment_transaction_id == txn["investment_transaction_id"]
            ).first()
            
            if existing:
                continue
            
            # Parse expiration date if present
            exp_date = None
            if txn.get("expiration_date"):
                try:
                    exp_date = datetime.strptime(txn["expiration_date"], "%Y-%m-%d")
                except:
                    pass
            
            new_txn = PlaidInvestmentTransaction(
                account_id=txn["account_id"],
                investment_transaction_id=txn["investment_transaction_id"],
                date=datetime.strptime(txn["date"], "%Y-%m-%d"),
                name=txn["name"],
                type=txn["type"] or "unknown",
                subtype=txn.get("subtype"),
                ticker_symbol=txn.get("ticker_symbol"),
                security_name=txn.get("security_name"),
                security_type=txn.get("security_type"),
                option_type=txn.get("option_type"),
                strike_price=str(txn["strike_price"]) if txn.get("strike_price") else None,
                expiration_date=exp_date,
                underlying_symbol=txn.get("underlying_symbol"),
                quantity=str(txn["quantity"]) if txn.get("quantity") else None,
                price=str(txn["price"]) if txn.get("price") else None,
                amount=str(txn["amount"]) if txn.get("amount") else None,
                fees=str(txn["fees"]) if txn.get("fees") else None,
                raw_data=txn,
            )
            db.add(new_txn)
            new_count += 1
        
        if new_count > 0:
            plaid_item.last_synced_at = datetime.utcnow()
            db.commit()
        
        return new_count
    
    def remove_item(self, plaid_item: PlaidItem, db: Session) -> bool:
        """
        Remove a Plaid item (disconnect account).
        
        Args:
            plaid_item: PlaidItem to remove
            db: Database session
            
        Returns:
            True if successfully removed
        """
        try:
            request = ItemRemoveRequest(access_token=plaid_item.access_token)
            self.client.item_remove(request)
            
            # Soft delete in database
            plaid_item.is_active = False
            plaid_item.updated_at = datetime.utcnow()
            db.commit()
            
            return True
        except Exception as e:
            logger.error(f"Failed to remove Plaid item: {e}")
            return False
    
    def get_all_items(self, db: Session) -> List[PlaidItem]:
        """Get all active Plaid items."""
        return db.query(PlaidItem).filter(PlaidItem.is_active == True).all()
    
    def get_item_by_id(self, item_id: int, db: Session) -> Optional[PlaidItem]:
        """Get a specific Plaid item by database ID."""
        return db.query(PlaidItem).filter(PlaidItem.id == item_id).first()


# Singleton instance
_plaid_service: Optional[PlaidService] = None


def get_plaid_service() -> PlaidService:
    """Get or create Plaid service instance."""
    global _plaid_service
    if _plaid_service is None:
        _plaid_service = PlaidService()
    return _plaid_service

