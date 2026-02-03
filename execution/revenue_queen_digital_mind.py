# ============================================================================
# MERGED FROM: revenue-swarm
# ORIGINAL FILE: queen_digital_mind.py
# MERGED DATE: 2026-01-16 03:18:36
# ============================================================================
"""
QUEEN Digital Mind - Native Implementation
Replaces Delphi.ai with local vector database and pattern recognition
"""

import os
import json
from datetime import datetime
from pathlib import Path

try:
    import chromadb
    from sentence_transformers import SentenceTransformer
except ImportError:
    print("Installing required packages...")
    os.system("pip install chromadb sentence-transformers")
    import chromadb
    from sentence_transformers import SentenceTransformer


class QueenDigitalMind:
    """
    Native implementation of Digital Mind capabilities
    - Knowledge indexing and retrieval
    - Pattern recognition
    - Self-annealing learning
    """
    
    def __init__(self, knowledge_path="./.hive-mind/knowledge"):
        """Initialize Digital Mind with vector database"""
        
        # Create knowledge directory
        Path(knowledge_path).mkdir(parents=True, exist_ok=True)
        
        # Initialize vector database
        self.chroma_client = chromadb.PersistentClient(path=knowledge_path)
        self.collection = self.chroma_client.get_or_create_collection(
            name="queen_knowledge",
            metadata={"description": "QUEEN's knowledge base"}
        )
        
        # Initialize embedder
        print("Loading embedding model...")
        self.embedder = SentenceTransformer('all-MiniLM-L6-v2')
        
        # Learning database
        self.learnings_path = Path(knowledge_path) / "learnings.json"
        self.learnings = self._load_learnings()
        
        print(f"âœ“ QUEEN Digital Mind initialized with {self.collection.count()} items")
    
    def index_content(self, content, content_type, metadata=None):
        """
        Index content into knowledge base
        
        Args:
            content: Text content to index
            content_type: Type (call_transcript, email, document, etc.)
            metadata: Additional metadata dict
        """
        if metadata is None:
            metadata = {}
        
        # Generate embedding
        embedding = self.embedder.encode(content)
        
        # Create unique ID
        doc_id = f"{content_type}_{datetime.now().timestamp()}"
        
        # Store in vector database
        self.collection.add(
            embeddings=[embedding.tolist()],
            documents=[content],
            metadatas=[{
                "type": content_type,
                "timestamp": datetime.now().isoformat(),
                **metadata
            }],
            ids=[doc_id]
        )
        
        print(f"âœ“ Indexed {content_type}: {doc_id}")
        return doc_id
    
    def retrieve_context(self, query, n_results=5, content_type=None):
        """
        Retrieve relevant context for decision-making
        
        Args:
            query: Search query
            n_results: Number of results to return
            content_type: Filter by content type
        
        Returns:
            List of relevant documents with metadata
        """
        # Generate query embedding
        query_embedding = self.embedder.encode(query)
        
        # Build where clause for filtering
        where = {"type": content_type} if content_type else None
        
        # Query vector database
        results = self.collection.query(
            query_embeddings=[query_embedding.tolist()],
            n_results=n_results,
            where=where
        )
        
        # Format results
        context = []
        if results['documents'] and results['documents'][0]:
            for i, doc in enumerate(results['documents'][0]):
                context.append({
                    "content": doc,
                    "metadata": results['metadatas'][0][i] if results['metadatas'] else {},
                    "distance": results['distances'][0][i] if results['distances'] else None
                })
        
        return context
    
    def learn_from_outcome(self, workflow, outcome, success=True, details=None):
        """
        Self-annealing: Learn from workflow outcomes
        
        Args:
            workflow: Workflow name
            outcome: Outcome description
            success: Whether workflow succeeded
            details: Additional details dict
        """
        if details is None:
            details = {}
        
        learning = {
            "workflow": workflow,
            "outcome": outcome,
            "success": success,
            "timestamp": datetime.now().isoformat(),
            **details
        }
        
        # Store in learnings database
        if workflow not in self.learnings:
            self.learnings[workflow] = {
                "successes": [],
                "failures": [],
                "success_rate": 0.0
            }
        
        if success:
            self.learnings[workflow]["successes"].append(learning)
            self._amplify_pattern(workflow, details)
        else:
            self.learnings[workflow]["failures"].append(learning)
            self._avoid_pattern(workflow, details)
        
        # Update success rate
        total = len(self.learnings[workflow]["successes"]) + len(self.learnings[workflow]["failures"])
        self.learnings[workflow]["success_rate"] = len(self.learnings[workflow]["successes"]) / total
        
        # Save learnings
        self._save_learnings()
        
        # Index learning for future retrieval
        self.index_content(
            json.dumps(learning),
            "learning",
            {"success": success, "workflow": workflow}
        )
        
        print(f"âœ“ Learned from {workflow}: {'SUCCESS' if success else 'FAILURE'}")
    
    def get_workflow_insights(self, workflow):
        """Get insights for a specific workflow"""
        if workflow not in self.learnings:
            return {"message": "No learnings for this workflow yet"}
        
        data = self.learnings[workflow]
        
        return {
            "workflow": workflow,
            "total_executions": len(data["successes"]) + len(data["failures"]),
            "success_rate": data["success_rate"],
            "recent_successes": data["successes"][-5:],
            "recent_failures": data["failures"][-5:],
            "recommendations": self._generate_recommendations(workflow)
        }
    
    def _amplify_pattern(self, workflow, details):
        """Amplify successful patterns"""
        # Store successful pattern for future use
        pattern_key = f"success_pattern_{workflow}"
        if pattern_key not in self.learnings:
            self.learnings[pattern_key] = []
        self.learnings[pattern_key].append(details)
    
    def _avoid_pattern(self, workflow, details):
        """Learn to avoid failed patterns"""
        # Store failed pattern to avoid in future
        pattern_key = f"failure_pattern_{workflow}"
        if pattern_key not in self.learnings:
            self.learnings[pattern_key] = []
        self.learnings[pattern_key].append(details)
    
    def _generate_recommendations(self, workflow):
        """Generate recommendations based on learnings"""
        if workflow not in self.learnings:
            return []
        
        data = self.learnings[workflow]
        recommendations = []
        
        if data["success_rate"] < 0.7:
            recommendations.append("Success rate below 70% - review failure patterns")
        
        if len(data["failures"]) > len(data["successes"]):
            recommendations.append("More failures than successes - consider workflow redesign")
        
        return recommendations
    
    def _load_learnings(self):
        """Load learnings from disk"""
        if self.learnings_path.exists():
            with open(self.learnings_path, 'r') as f:
                return json.load(f)
        return {}
    
    def _save_learnings(self):
        """Save learnings to disk"""
        with open(self.learnings_path, 'w') as f:
            json.dump(self.learnings, f, indent=2)
    
    def index_directory(self, directory_path, content_type="document"):
        """Index all text files in a directory"""
        directory = Path(directory_path)
        indexed = 0
        
        for file_path in directory.rglob("*.txt"):
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                self.index_content(
                    content,
                    content_type,
                    {"filename": file_path.name, "path": str(file_path)}
                )
                indexed += 1
        
        print(f"âœ“ Indexed {indexed} files from {directory_path}")
        return indexed


def main():
    """Test QUEEN Digital Mind"""
    print("=" * 60)
    print("QUEEN DIGITAL MIND - Native Implementation")
    print("=" * 60)
    
    # Initialize
    queen = QueenDigitalMind()
    
    # Test indexing
    print("\n1. Testing content indexing...")
    queen.index_content(
        "Customer complained about slow response time. Resolved by upgrading server.",
        "support_ticket",
        {"customer": "Acme Corp", "severity": "high"}
    )
    
    queen.index_content(
        "Successful demo with TechCorp. They're interested in enterprise plan.",
        "sales_note",
        {"company": "TechCorp", "deal_stage": "demo"}
    )
    
    # Test retrieval
    print("\n2. Testing context retrieval...")
    results = queen.retrieve_context("server performance issues")
    print(f"Found {len(results)} relevant items:")
    for r in results:
        print(f"  - {r['content'][:80]}...")
    
    # Test learning
    print("\n3. Testing self-annealing...")
    queen.learn_from_outcome(
        "lead_processing",
        "Successfully processed lead and booked meeting",
        success=True,
        details={"lead_source": "website", "response_time": "2min"}
    )
    
    queen.learn_from_outcome(
        "lead_processing",
        "Failed to book meeting - lead not qualified",
        success=False,
        details={"lead_source": "cold_email", "reason": "wrong_icp"}
    )
    
    # Get insights
    print("\n4. Getting workflow insights...")
    insights = queen.get_workflow_insights("lead_processing")
    print(json.dumps(insights, indent=2))
    
    print("\n" + "=" * 60)
    print("âœ“ QUEEN Digital Mind test complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()

