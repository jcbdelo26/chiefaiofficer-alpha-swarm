# ============================================================================
# MERGED FROM: revenue-swarm
# ORIGINAL FILE: scout_intent_detection.py
# MERGED DATE: 2026-01-16 03:18:36
# ============================================================================
"""
SCOUT Intent Detection - Native Implementation
Replaces Artisan AVA's intent signal detection with Exa Search
"""

import os
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv

try:
    from exa_py import Exa
except ImportError:
    print("Installing exa-py...")
    os.system("pip install exa-py")
    from exa_py import Exa

load_dotenv()


class ScoutIntentDetection:
    """
    Native implementation of intent signal detection (AVA function)
    - Funding announcements
    - Hiring activity
    - Leadership changes
    - Product launches
    - Website activity
    """
    
    def __init__(self):
        """Initialize with Exa API"""
        api_key = os.getenv('EXA_API_KEY')
        if not api_key:
            raise ValueError("EXA_API_KEY not found in environment")
        
        self.exa = Exa(api_key=api_key)
        print("âœ“ SCOUT Intent Detection initialized")
    
    def detect_intent_signals(self, company_name, company_domain=None):
        """
        Detect buying intent signals for a company
        
        Args:
            company_name: Company name
            company_domain: Company domain (optional)
        
        Returns:
            Dict with intent signals and score
        """
        print(f"\nðŸ” Detecting intent signals for {company_name}...")
        
        signals = {
            "company": company_name,
            "domain": company_domain,
            "timestamp": datetime.now().isoformat(),
            "funding": self._check_funding(company_name),
            "hiring": self._check_hiring(company_name),
            "leadership_changes": self._check_leadership_changes(company_name),
            "product_launches": self._check_product_launches(company_name),
            "news_mentions": self._check_news_mentions(company_name),
            "intent_score": 0
        }
        
        # Calculate overall intent score
        signals['intent_score'] = self._calculate_intent_score(signals)
        
        # Determine priority
        signals['priority'] = self._determine_priority(signals['intent_score'])
        
        print(f"âœ“ Intent score: {signals['intent_score']}/100 ({signals['priority']})")
        
        return signals
    
    def _check_funding(self, company_name):
        """Check for recent funding announcements"""
        print("  Checking funding announcements...")
        
        query = f"{company_name} funding announcement OR series OR raised OR investment"
        
        try:
            results = self.exa.search(
                query,
                num_results=5,
                start_published_date=(datetime.now() - timedelta(days=90)).isoformat()
            )
            
            detected = len(results.results) > 0
            details = [
                {
                    "title": r.title,
                    "url": r.url,
                    "published": r.published_date
                }
                for r in results.results
            ]
            
            if detected:
                print(f"    âœ“ Found {len(details)} funding signals")
            
            return {
                "detected": detected,
                "count": len(details),
                "details": details
            }
        except Exception as e:
            print(f"    âœ— Error checking funding: {e}")
            return {"detected": False, "count": 0, "details": [], "error": str(e)}
    
    def _check_hiring(self, company_name):
        """Check for hiring activity"""
        print("  Checking hiring activity...")
        
        query = f"{company_name} hiring OR job openings OR we're hiring OR careers"
        
        try:
            results = self.exa.search(
                query,
                num_results=5,
                start_published_date=(datetime.now() - timedelta(days=30)).isoformat()
            )
            
            detected = len(results.results) > 0
            details = [
                {
                    "title": r.title,
                    "url": r.url,
                    "published": r.published_date
                }
                for r in results.results
            ]
            
            if detected:
                print(f"    âœ“ Found {len(details)} hiring signals")
            
            return {
                "detected": detected,
                "count": len(details),
                "details": details
            }
        except Exception as e:
            print(f"    âœ— Error checking hiring: {e}")
            return {"detected": False, "count": 0, "details": [], "error": str(e)}
    
    def _check_leadership_changes(self, company_name):
        """Check for leadership changes"""
        print("  Checking leadership changes...")
        
        query = f"{company_name} new CEO OR new CTO OR new VP OR joins as OR appointed"
        
        try:
            results = self.exa.search(
                query,
                num_results=5,
                start_published_date=(datetime.now() - timedelta(days=60)).isoformat()
            )
            
            detected = len(results.results) > 0
            details = [
                {
                    "title": r.title,
                    "url": r.url,
                    "published": r.published_date
                }
                for r in results.results
            ]
            
            if detected:
                print(f"    âœ“ Found {len(details)} leadership change signals")
            
            return {
                "detected": detected,
                "count": len(details),
                "details": details
            }
        except Exception as e:
            print(f"    âœ— Error checking leadership: {e}")
            return {"detected": False, "count": 0, "details": [], "error": str(e)}
    
    def _check_product_launches(self, company_name):
        """Check for product launches"""
        print("  Checking product launches...")
        
        query = f"{company_name} launches OR announces OR releases new OR unveils"
        
        try:
            results = self.exa.search(
                query,
                num_results=5,
                start_published_date=(datetime.now() - timedelta(days=30)).isoformat()
            )
            
            detected = len(results.results) > 0
            details = [
                {
                    "title": r.title,
                    "url": r.url,
                    "published": r.published_date
                }
                for r in results.results
            ]
            
            if detected:
                print(f"    âœ“ Found {len(details)} product launch signals")
            
            return {
                "detected": detected,
                "count": len(details),
                "details": details
            }
        except Exception as e:
            print(f"    âœ— Error checking product launches: {e}")
            return {"detected": False, "count": 0, "details": [], "error": str(e)}
    
    def _check_news_mentions(self, company_name):
        """Check for general news mentions"""
        print("  Checking news mentions...")
        
        query = f"{company_name}"
        
        try:
            results = self.exa.search(
                query,
                num_results=10,
                start_published_date=(datetime.now() - timedelta(days=7)).isoformat()
            )
            
            detected = len(results.results) > 0
            details = [
                {
                    "title": r.title,
                    "url": r.url,
                    "published": r.published_date
                }
                for r in results.results
            ]
            
            if detected:
                print(f"    âœ“ Found {len(details)} news mentions")
            
            return {
                "detected": detected,
                "count": len(details),
                "details": details
            }
        except Exception as e:
            print(f"    âœ— Error checking news: {e}")
            return {"detected": False, "count": 0, "details": [], "error": str(e)}
    
    def _calculate_intent_score(self, signals):
        """
        Calculate overall intent score (0-100)
        
        Scoring:
        - Funding: 30 points
        - Hiring: 25 points
        - Leadership changes: 20 points
        - Product launches: 15 points
        - News mentions: 10 points
        """
        score = 0
        
        if signals['funding']['detected']:
            score += 30
        
        if signals['hiring']['detected']:
            score += 25
        
        if signals['leadership_changes']['detected']:
            score += 20
        
        if signals['product_launches']['detected']:
            score += 15
        
        if signals['news_mentions']['detected']:
            score += 10
        
        return min(score, 100)
    
    def _determine_priority(self, intent_score):
        """Determine priority based on intent score"""
        if intent_score >= 70:
            return "HIGH"
        elif intent_score >= 40:
            return "MEDIUM"
        else:
            return "LOW"
    
    def batch_detect(self, companies):
        """
        Detect intent signals for multiple companies
        
        Args:
            companies: List of dicts with 'name' and optional 'domain'
        
        Returns:
            List of intent signal results
        """
        results = []
        
        for company in companies:
            signals = self.detect_intent_signals(
                company.get('name'),
                company.get('domain')
            )
            results.append(signals)
        
        # Sort by intent score
        results.sort(key=lambda x: x['intent_score'], reverse=True)
        
        return results
    
    def export_results(self, signals, output_file):
        """Export intent signals to JSON file"""
        with open(output_file, 'w') as f:
            json.dump(signals, f, indent=2)
        print(f"âœ“ Exported results to {output_file}")


def main():
    """Test SCOUT Intent Detection"""
    print("=" * 60)
    print("SCOUT INTENT DETECTION - Native Implementation")
    print("=" * 60)
    
    # Initialize
    scout = ScoutIntentDetection()
    
    # Test single company
    print("\n1. Testing single company detection...")
    signals = scout.detect_intent_signals("Salesforce")
    
    print("\nðŸ“Š Results:")
    print(f"  Company: {signals['company']}")
    print(f"  Intent Score: {signals['intent_score']}/100")
    print(f"  Priority: {signals['priority']}")
    print(f"  Funding: {'âœ“' if signals['funding']['detected'] else 'âœ—'}")
    print(f"  Hiring: {'âœ“' if signals['hiring']['detected'] else 'âœ—'}")
    print(f"  Leadership Changes: {'âœ“' if signals['leadership_changes']['detected'] else 'âœ—'}")
    print(f"  Product Launches: {'âœ“' if signals['product_launches']['detected'] else 'âœ—'}")
    
    # Test batch detection
    print("\n2. Testing batch detection...")
    companies = [
        {"name": "OpenAI"},
        {"name": "Anthropic"},
        {"name": "Google"}
    ]
    
    batch_results = scout.batch_detect(companies)
    
    print("\nðŸ“Š Batch Results (sorted by intent score):")
    for result in batch_results:
        print(f"  {result['company']}: {result['intent_score']}/100 ({result['priority']})")
    
    # Export results
    print("\n3. Exporting results...")
    scout.export_results(signals, "./.hive-mind/intent_signals.json")
    
    print("\n" + "=" * 60)
    print("âœ“ SCOUT Intent Detection test complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()

