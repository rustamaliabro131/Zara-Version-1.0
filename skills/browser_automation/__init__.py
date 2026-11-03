"""
skills/browser_automation/ — Browser automation task workflows for Zara.

Contains platform-specific workflows:
- Upwork Bidder (proposal generation, bid rates, submission)
- Amazon KDP Publisher (eBook metadata, manuscript & cover upload, pricing)
- Fiverr Gig Creator (title, categories, search tags, description, pricing)
- Facebook Poster (feed / Creator Studio, text content, media attachment, publish)
- Daraz Shopper (product search, selection, cart management)
"""

from skills.browser_automation.upwork_bidder import submit_upwork_proposal
from skills.browser_automation.amazon_kdp_publisher import publish_kdp_ebook
from skills.browser_automation.fiverr_gig_creator import create_fiverr_gig
from skills.browser_automation.facebook_poster import post_to_facebook
from skills.browser_automation.daraz_shopper import shop_daraz

__all__ = [
    "submit_upwork_proposal",
    "publish_kdp_ebook",
    "create_fiverr_gig",
    "post_to_facebook",
    "shop_daraz",
]
