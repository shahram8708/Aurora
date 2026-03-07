import uuid
from flask import current_app
from app.extensions import db
from app.models import AdsRevenue


def _as_uuid(value):
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


def _defaults():
    rpm = int(current_app.config.get("ADS_RPM_PAISE", 1200))
    rpc = int(current_app.config.get("ADS_RPC_PAISE", 2500))
    fee_bps = int(current_app.config.get("ADS_PLATFORM_FEE_BPS", 1500))
    return rpm, rpc, fee_bps


def _revenue_row(creator_id, campaign_id, rpm, rpc):
    row = AdsRevenue.query.filter_by(creator_id=creator_id, campaign_id=campaign_id).first()
    if not row:
        row = AdsRevenue(creator_id=creator_id, campaign_id=campaign_id, rpm=rpm, rpc=rpc)
        db.session.add(row)
    if not row.rpm:
        row.rpm = rpm
    if not row.rpc:
        row.rpc = rpc
    # Normalize numeric fields to avoid None before increments
    row.impressions = row.impressions or 0
    row.clicks = row.clicks or 0
    row.earnings = row.earnings or 0
    row.platform_fees = row.platform_fees or 0
    return row


def record_impressions(campaigns, viewer_id=None):
    if not campaigns:
        return
    viewer_uuid = _as_uuid(viewer_id)
    rpm, rpc, fee_bps = _defaults()
    counts = {}
    for camp in campaigns:
        if not camp or not getattr(camp, "id", None) or not getattr(camp, "creator_id", None):
            continue
        if viewer_uuid and camp.creator_id == viewer_uuid:
            continue
        counts[camp.id] = counts.get(camp.id, 0) + 1
    if not counts:
        return
    for camp in campaigns:
        if camp.id not in counts:
            continue
        row = _revenue_row(camp.creator_id, camp.id, rpm, rpc)
        impressions = counts[camp.id]
        row.impressions = (row.impressions or 0) + impressions
        earned = int((impressions * (row.rpm or rpm)) / 1000)
        row.earnings = (row.earnings or 0) + earned
        row.platform_fees = (row.platform_fees or 0) + int(earned * fee_bps / 10000)
    db.session.commit()


def record_click(campaign, viewer_id=None):
    if not campaign or not getattr(campaign, "id", None) or not getattr(campaign, "creator_id", None):
        return
    viewer_uuid = _as_uuid(viewer_id)
    if viewer_uuid and campaign.creator_id == viewer_uuid:
        return
    rpm, rpc, fee_bps = _defaults()
    row = _revenue_row(campaign.creator_id, campaign.id, rpm, rpc)
    row.clicks = (row.clicks or 0) + 1
    earned = row.rpc or rpc
    row.earnings += earned
    row.platform_fees += int(earned * fee_bps / 10000)
    db.session.commit()
