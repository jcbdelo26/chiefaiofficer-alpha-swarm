"""
Messaging Strategy Module
=========================
Stores all email angles (Tiers 1-3) and logic to select the best one based on signals.
Templates extracted from: HEAD_OF_SALES_REQUIREMENTS 01.26.2026

Selection Logic:
1. HIRING Signal -> Angle C (Hiring Trigger / Bridge Strategy)
2. TECH_STACK Signal -> Angle B (Industry-Specific) for Tier 1, Angle A for Tier 2
3. HIGH_INTENT Signal -> Angle D (Value-First / Soft CTA)
4. Default -> Angle A (Primary Value Prop)
"""

from typing import Dict, Any, Tuple
from core.signal_detector import SignalType, DetectedSignal
from core.email_signature import enforce_html_signature, CALL_LINK

# =============================================================================
# CAN-SPAM FOOTER (Required on ALL emails)
# =============================================================================
CAN_SPAM_FOOTER = """
<p style="font-size: 11px; color: #666; margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee; text-align: center;">
    We only reach out to professionals we believe can lead AI strategy inside their organizations.
    If this isn't you, or now's not the right time, just <a href="mailto:support@chiefaiofficer.com?subject=Unsubscribe">click here</a> and I'll take care of it personally.<br><br>
    <strong>Chief AI Officer Inc.</strong><br>
    5700 Harper Dr, Suite 210, Albuquerque, NM 87109<br>
    <a href="mailto:support@chiefaiofficer.com">support@chiefaiofficer.com</a><br>
    Copyright © 2026 Chief AI Officer. All rights reserved.
</p>
"""

BOOK_URL = CALL_LINK


class MessagingStrategy:
    """Manages email templates and selection logic."""
    
    def __init__(self):
        self.templates = self._load_templates()

    def select_template(self, lead: Dict[str, Any], primary_signal: DetectedSignal) -> Tuple[str, str, str]:
        """
        Select the best template based on Lead Tier and Primary Signal.
        
        Returns:
            (template_id, subject, body)
        """
        tier = lead.get("tier", 3)
        
        if tier == 1:
            return self._select_tier_1(primary_signal, lead)
        elif tier == 2:
            return self._select_tier_2(primary_signal, lead)
        else:
            return self._select_tier_3(primary_signal, lead)

    def _select_tier_1(self, signal: DetectedSignal, lead: Dict[str, Any]) -> Tuple[str, str, str]:
        """Tier 1 Strategy: CEO/Founder/President"""
        if signal.type == SignalType.HIRING:
            return self._get_template("tier1_angle_c", lead)  # Hiring Trigger
        elif signal.type == SignalType.TECH_STACK:
            return self._get_template("tier1_angle_b", lead)  # Industry-Specific
        elif signal.type == SignalType.HIGH_INTENT:
            return self._get_template("tier1_angle_d", lead)  # Value/Soft CTA
        else:
            return self._get_template("tier1_angle_a", lead)  # Executive Buy-In (Default)

    def _select_tier_2(self, signal: DetectedSignal, lead: Dict[str, Any]) -> Tuple[str, str, str]:
        """Tier 2 Strategy: CTO/CIO/VP Ops"""
        if signal.type == SignalType.TECH_STACK:
            return self._get_template("tier2_angle_a", lead)  # Tech Stack Play
        elif signal.type == SignalType.HIRING:
            return self._get_template("tier2_angle_c", lead)  # Innovation Champion
        else:
            return self._get_template("tier2_angle_b", lead)  # Ops Efficiency (Default)

    def _select_tier_3(self, signal: DetectedSignal, lead: Dict[str, Any]) -> Tuple[str, str, str]:
        """Tier 3 Strategy: Directors/Managers/SMB"""
        if signal.type == SignalType.HIGH_INTENT:
            return self._get_template("tier3_angle_c", lead)  # Competitor FOMO
        elif signal.type == SignalType.TECH_STACK:
            return self._get_template("tier3_angle_b", lead)  # Time Savings
        else:
            return self._get_template("tier3_angle_a", lead)  # Quick Win (Default)

    def _get_template(self, template_id: str, lead: Dict[str, Any] = None) -> Tuple[str, str, str]:
        """Retrieve template by ID and enforce canonical signature/footer."""
        tmpl = self.templates.get(template_id)
        if not tmpl:
            # Fallback
            return "fallback", "Quick question", enforce_html_signature("<p>Hi {first_name}, connecting...</p>")

        body_with_footer = enforce_html_signature(tmpl["body"])
        return template_id, tmpl["subject"], body_with_footer

    def get_followup_template(self, followup_number: int, lead: Dict[str, Any]) -> Tuple[str, str, str]:
        """Get follow-up template (Day 3-4 or Day 7)."""
        if followup_number == 1:
            return self._get_template("followup_1", lead)
        else:
            return self._get_template("followup_2", lead)

    def _load_templates(self) -> Dict[str, Dict[str, str]]:
        """
        Official templates from Head of Sales Requirements (Jan 2026).
        All templates include proper formatting and CTAs.
        """
        return {
            # =================================================================
            # TIER 1: C-Suite / Founders (CEO, COO, President, Founder)
            # =================================================================
            "tier1_angle_a": {
                "name": "Executive Buy-In (Fractional CAIO Gap)",
                "subject": "AI Roadmap for {company}",
                "body": """
<p>Hi {first_name},</p>

<p>Seeing a lot of {industry} firms stuck in "AI research mode" without moving to implementation.</p>

<p>Usually, it's because the CTO is buried in legacy tech and there's no dedicated AI lead to drive the strategy forward.</p>

<p>We act as your Fractional Chief AI Officer to move {company} from curiosity to ROI—typically in 90 days.</p>

<p><strong>What that looks like:</strong></p>
<ul>
<li>Day 1: One-day M.A.P. Bootcamp (your team leaves with an AI-ready action plan)</li>
<li>Days 2-90: We embed with your team, build the workflows, and measure results</li>
<li>Guarantee: Measurable ROI, or you don't pay the next phase</li>
</ul>

<p>Worth a brief chat on how we're doing this for similar {industry} companies?</p>

<p>Best,<br>
<strong>Dani Apgar</strong><br>
Chief AI Officer<br>
<a href="{book_url}">Book a 30 min. briefing</a></p>
""".replace("{book_url}", BOOK_URL)
            },
            
            "tier1_angle_b": {
                "name": "Industry-Specific (YPO/Construction/Manufacturing)",
                "subject": "AI in {industry} / {company}",
                "body": """
<p>Hi {first_name},</p>

<p>Many {industry} CEOs I speak with are frustrated by thin margins and operational inefficiency.</p>

<p>The fix we're seeing work: AI automating the back-office "drudge work"—project estimation, invoicing, scheduling, reporting—so your team can focus on revenue.</p>

<p><strong>Example:</strong> A 150-person {industry} firm saved 300+ hours in 30 days and saw a 27% productivity boost after our 90-day AI pilot.</p>

<p>Are you open to seeing a quick breakdown of the workflow we built for them?</p>

<p>Best,<br>
<strong>Dani Apgar</strong><br>
Chief AI Officer<br>
<a href="{book_url}">Book 30-min Call</a></p>
""".replace("{book_url}", BOOK_URL)
            },
            
            "tier1_angle_c": {
                "name": "Hiring Trigger (Bridge Strategy)",
                "subject": "Re: {company}'s AI hiring",
                "body": """
<p>Hi {first_name},</p>

<p>Noticed you're hiring for <strong>AI and data roles</strong> at {company}. Smart move.</p>

<p>But here's what we typically see: it takes 4–6 months before that hire makes real impact—between sourcing, onboarding, and ramp-up.</p>

<p>We step in as your fractional AI leadership now—so your incoming hire hits the ground running on Day 1.</p>

<p><strong>In just 90 days, we:</strong></p>
<ul>
<li>Define your AI roadmap before the hire starts</li>
<li>Train your current team on AI fundamentals</li>
<li>Build and deploy your first automated workflows</li>
<li>Hand off a documented AI playbook to your new AI lead</li>
</ul>

<p>Open to a quick 30-min bridge strategy call?</p>

<p>Best,<br>
<strong>Dani Apgar</strong><br>
Chief AI Officer<br>
<a href="{book_url}">Book Bridge Strategy Call</a></p>
""".replace("{book_url}", BOOK_URL)
            },
            
            "tier1_angle_d": {
                "name": "Value-First (Soft CTA)",
                "subject": "2-minute AI readiness check for {company}",
                "body": """
<p>Hi {first_name},</p>

<p>I put together a 2-minute "AI Readiness" audit for {industry} leaders.</p>

<p>It covers the 3 biggest low-hanging fruit automation wins we're seeing right now—ones that typically save 10-20 hours per week per team member.</p>

<p>Mind if I send the link over?</p>

<p>(No pitch, no 30-minute demo request—just a quick self-assessment.)</p>

<p>Best,<br>
<strong>Dani Apgar</strong><br>
Chief AI Officer<br>
ChiefAIOfficer.com</p>
"""
            },
            
            # =================================================================
            # TIER 2: Strategic Influencers (CTO, CIO, VP Ops, Head of Innovation)
            # =================================================================
            "tier2_angle_a": {
                "name": "Tech Stack Integration Play",
                "subject": "{first_name} - AI for {company}'s tech stack",
                "body": """
<p>Hi {first_name},</p>

<p>I noticed {company} is using {tech_stack}—we actually have a specific AI integration playbook for that stack.</p>

<p>Most {title} roles I talk to are seeing two blockers:</p>
<ol>
<li>The CTO is buried in legacy tech maintenance</li>
<li>No dedicated AI strategy lead to drive implementation</li>
</ol>

<p>We bridge that gap as your Fractional Chief AI Officer—moving from "AI pilot" to production workflows in 90 days.</p>

<p><strong>What teams like yours are automating:</strong></p>
<ul>
<li>Lead enrichment & qualification (from raw data to booked meetings)</li>
<li>Document processing & extraction (invoices, contracts, reports)</li>
<li>Customer support triage (route, respond, escalate)</li>
</ul>

<p>Would it be helpful if I shared the AI tech stack we're seeing work best for {industry}?</p>

<p>Cheers,<br>
<strong>Dani Apgar</strong><br>
Chief AI Officer<br>
<a href="{book_url}">Book 30-min Demo</a></p>
""".replace("{book_url}", BOOK_URL)
            },
            
            "tier2_angle_b": {
                "name": "Operations Efficiency Play",
                "subject": "{company}'s operational efficiency",
                "body": """
<p>Hi {first_name},</p>

<p>The teams we work with are seeing 40-60% time savings on operational tasks using AI automation.</p>

<p><strong>Specifically:</strong></p>
<ul>
<li>One 150-person firm saved 300+ hours in 30 days on administrative work</li>
<li>A 7-person pilot team saw 27% productivity boost in the first month</li>
<li>AI now handles the work of 20+ staff in Operations at one of our travel clients</li>
</ul>

<p>The pattern: start with high-volume, low-complexity tasks (data entry, scheduling, reporting), prove ROI in 30 days, then expand.</p>

<p>We call it the M.A.P. framework: <strong>Measure → Automate → Prove</strong></p>

<p>Open to a brief sync next Tuesday, or should I just send over a one-pager for now?</p>

<p>Cheers,<br>
<strong>Dani Apgar</strong><br>
Chief AI Officer<br>
<a href="{book_url}">Book Quick Call</a></p>
""".replace("{book_url}", BOOK_URL)
            },
            
            "tier2_angle_c": {
                "name": "Innovation/Transformation Champion Play",
                "subject": "AI transformation at {company}",
                "body": """
<p>Hi {first_name},</p>

<p>75%+ of AI pilots stall before ROI is proven.</p>

<p>The root cause we see: insufficient governance and process integration. CFOs see spend but not savings. Teams focus on "AI chatbots" instead of operational transformation.</p>

<p>We fix this by building an <strong>AI Council</strong> inside your company—internal champions from every department who drive adoption from within.</p>

<p><strong>Our 90-day approach:</strong></p>
<ol>
<li>Day 1: Executive bootcamp (your team leaves AI-ready)</li>
<li>Weeks 2-8: We co-pilot with your AI Council, build the workflows</li>
<li>Weeks 9-12: Measure ROI, hand off the playbook</li>
</ol>

<p>If the M.A.P. cycle doesn't deliver tangible savings, you don't pay the next phase.</p>

<p>Mind if I send over a 2-minute video on how we do this?</p>

<p>Cheers,<br>
<strong>Dani Apgar</strong><br>
Chief AI Officer<br>
ChiefAIOfficer.com</p>
"""
            },
            
            # =================================================================
            # TIER 3: General Prospects (Directors, Managers, SMB 20-50 employees)
            # =================================================================
            "tier3_angle_a": {
                "name": "Quick Win (One Workflow Starter)",
                "subject": "Quick idea for {company}",
                "body": """
<p>Hi {first_name},</p>

<p>Most {industry} teams I talk to have one workflow that eats up way too much time—usually something like data entry, reporting, or lead research.</p>

<p>We help companies like {company} automate that one thing first. No 6-month project. Just pick the biggest time-waster and fix it.</p>

<p><strong>Example:</strong> A 25-person {industry} company automated their weekly reporting and got 8 hours back per person, per month.</p>

<p>Worth a quick look?</p>

<p>Reply "yes" and I'll send a 2-minute breakdown of how we do it.</p>

<p>Best,<br>
<strong>Dani Apgar</strong><br>
Chief AI Officer<br>
ChiefAIOfficer.com</p>
"""
            },
            
            "tier3_angle_b": {
                "name": "Time Savings (Get Your Weekends Back)",
                "subject": "{first_name} - 10 hours back per week",
                "body": """
<p>Hi {first_name},</p>

<p>The teams I work with typically waste 10-15 hours per week on tasks that should be automated: data entry, status updates, scheduling, and reporting.</p>

<p>We use AI agents to handle that—not a "chatbot" but actual workflow automation that runs 24/7.</p>

<p><strong>Quick wins we see for {industry} teams:</strong></p>
<ul>
<li>Auto-updating spreadsheets and dashboards</li>
<li>Lead research done overnight (you wake up to qualified lists)</li>
<li>Follow-up emails sent at the right time, automatically</li>
</ul>

<p>No huge IT project. Start with one workflow, prove it works, expand from there.</p>

<p>Should I send over a quick video showing how this works for teams your size?</p>

<p>Best,<br>
<strong>Dani Apgar</strong><br>
Chief AI Officer<br>
ChiefAIOfficer.com</p>
"""
            },
            
            "tier3_angle_c": {
                "name": "Competitor FOMO (Others Are Already Doing This)",
                "subject": "What {industry} teams are automating",
                "body": """
<p>Hi {first_name},</p>

<p>I've been working with a few {industry} companies lately, and there's a pattern:</p>

<p>The ones pulling ahead are automating the "invisible work"—the research, the data entry, the follow-ups that eat up 40-60% of everyone's week.</p>

<p><strong>What they're automating:</strong></p>
<ul>
<li>Lead research and scoring (AI does it overnight)</li>
<li>Proposal drafts and first-pass content</li>
<li>Client onboarding workflows</li>
<li>Reporting and status updates</li>
</ul>

<p>Not asking you to rip out your tech stack. Just add a layer of AI that handles the repetitive stuff.</p>

<p>Curious if {company} has looked into this yet?</p>

<p>Just reply "show me"—I'll send a quick breakdown of what we're seeing work.</p>

<p>Best,<br>
<strong>Dani Apgar</strong><br>
Chief AI Officer<br>
ChiefAIOfficer.com</p>
"""
            },
            
            "tier3_angle_d": {
                "name": "DIY Resource (Ungated Value Play)",
                "subject": "Free AI checklist for {industry}",
                "body": """
<p>Hi {first_name},</p>

<p>I put together a 1-page checklist of the 5 "quick win" AI automations that work best for {industry} teams under 50 people.</p>

<p>No fluff, no 30-minute demo required—just actionable stuff you can implement yourself or hand to your ops person.</p>

<p><strong>Includes:</strong></p>
<ul>
<li>Top 5 workflows to automate first (and why)</li>
<li>Tools that work for small budgets (<$100/month)</li>
<li>Common mistakes to avoid</li>
</ul>

<p>Mind if I send it over?</p>

<p>(No strings attached—it's genuinely useful even if we never talk.)</p>

<p>Best,<br>
<strong>Dani Apgar</strong><br>
Chief AI Officer<br>
ChiefAIOfficer.com</p>
"""
            },
            
            # =================================================================
            # FOLLOW-UP SEQUENCES
            # =================================================================
            "followup_1": {
                "name": "Follow-Up 1 (Day 3-4 Value-First)",
                "subject": "Re: {original_subject}",
                "body": """
<p>Hi {first_name},</p>

<p>Following up on my note from earlier this week.</p>

<p>I put together a 2-minute "AI Readiness" audit specifically for {industry} leaders.</p>

<p>It covers the 3 biggest low-hanging fruit automation wins we're seeing right now—ones that typically save 10-20 hours per week per team member.</p>

<p>Mind if I send the link over?</p>

<p>(No pitch, no 30-minute demo request—just a quick self-assessment you can complete in under 3 minutes.)</p>

<p>Best,<br>
<strong>Dani Apgar</strong><br>
Chief AI Officer<br>
ChiefAIOfficer.com</p>
"""
            },
            
            "followup_2": {
                "name": "Follow-Up 2 (Day 7 Break-Up)",
                "subject": "Closing the loop / {company}",
                "body": """
<p>Hi {first_name},</p>

<p>I haven't heard back, so I'm assuming AI implementation isn't a top-three priority for {company} this quarter.</p>

<p>I'll take this off my follow-up list.</p>

<p>If things change down the road—whether it's a new budget cycle, a strategic shift, or just curiosity—you know where to find me.</p>

<p>Wishing you and the {company} team continued success.</p>

<p>Best,<br>
<strong>Dani Apgar</strong><br>
Chief AI Officer<br>
ChiefAIOfficer.com</p>
"""
            }
        }
