"""
FEFO Service - First Expired First Out
Core business logic for grocery store
"""
from sqlalchemy.orm import Session
from sqlalchemy import asc, or_
from typing import List, Tuple
from datetime import date
from decimal import Decimal
from app.models.batch import Batch

def sellable_batch_filter():
    """Batches that may be sold: in stock and not past their expiry date.

    A batch whose expiry_date is today is still sellable (expiry is end-of-day);
    only batches that expired on an earlier day are excluded. Batches with no
    expiry date (non-expiry-controlled goods) are always sellable.
    """
    return or_(Batch.expiry_date.is_(None), Batch.expiry_date >= date.today())

def get_fefo_batches(db: Session, product_id: int, location_id: int = None) -> List[Batch]:
    """Get batches ordered by expiry date (FEFO)"""
    q = db.query(Batch).filter(
        Batch.product_id == product_id,
        Batch.quantity_available > 0,
        sellable_batch_filter(),
    )
    if location_id:
        q = q.filter(Batch.warehouse_location_id == location_id)
    # NULLS LAST for products without expiry
    return q.order_by(Batch.expiry_date.asc().nulls_last(), Batch.created_at.asc()).all()

def allocate_fefo(batches: List[Batch], quantity: Decimal) -> List[Tuple[Batch, Decimal]]:
    """
    Allocate quantity using FEFO
    Returns list of (batch, quantity_to_take)
    """
    remaining = quantity
    allocations = []
    
    for batch in batches:
        if remaining <= 0:
            break
        take = min(remaining, batch.quantity_available)
        if take > 0:
            allocations.append((batch, take))
            remaining -= take
    
    if remaining > 0:
        raise ValueError(f"Niewystarczający stan. Brakuje {remaining}. Dostępne: {quantity - remaining}")
    
    return allocations

def check_fefo_violation(db: Session, product_id: int, requested_batch_id: int) -> bool:
    """
    Check if user tries to use later batch when older exists
    Returns True if violation
    """
    requested_batch = db.query(Batch).filter(Batch.id == requested_batch_id).first()
    if not requested_batch:
        return False
    
    # Find oldest batch with stock
    oldest = db.query(Batch).filter(
        Batch.product_id == product_id,
        Batch.quantity_available > 0,
        Batch.id != requested_batch_id
    ).order_by(Batch.expiry_date.asc().nulls_last()).first()
    
    if not oldest:
        return False
    
    # If oldest expiry is before requested, it's a violation
    if oldest.expiry_date and requested_batch.expiry_date:
        return oldest.expiry_date < requested_batch.expiry_date
    elif oldest.expiry_date and not requested_batch.expiry_date:
        # Oldest has expiry, requested has none -> violation (should use dated first)
        return True
    
    return False
