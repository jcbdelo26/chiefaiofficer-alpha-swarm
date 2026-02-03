# Tone Matching Directive

## Purpose
Ensure all automated communications match the prospect's communication style and maintain consistent, professional tone throughout the sales process.

---

## Tone Categories

### 1. Formal Professional
**Indicators:**
- Full sentences, proper grammar
- Formal salutations ("Dear", "Best regards")
- Job title in signature
- No emojis or casual language

**Our Response Style:**
```
Dear John,

Thank you for your response. I would be pleased to schedule 
a call at your earliest convenience.

Please find below three available time slots:
• Tuesday, January 28th at 10:00 AM EST
• Wednesday, January 29th at 2:00 PM EST
• Thursday, January 30th at 11:00 AM EST

I look forward to our conversation.

Best regards,
[Name]
```

### 2. Business Casual
**Indicators:**
- Complete sentences but relaxed
- "Hi" instead of "Dear"
- Occasional contractions
- Friendly but professional

**Our Response Style:**
```
Hi John,

Thanks for getting back to me! I'd love to set up a call.

Here are a few times that work on my end:
• Tuesday 1/28 at 10am ET
• Wednesday 1/29 at 2pm ET
• Thursday 1/30 at 11am ET

Let me know what works best for you!

Best,
[Name]
```

### 3. Casual/Friendly
**Indicators:**
- Short sentences, fragments okay
- First names only
- Emojis sometimes used
- Conversational

**Our Response Style:**
```
Hey John!

Great to hear from you - let's get something on the calendar.

How about:
- Tuesday 10am?
- Wednesday 2pm?
- Thursday 11am?

Any of those work?

[Name]
```

### 4. Direct/Efficient
**Indicators:**
- Very short messages
- Bullet points
- No pleasantries
- Gets to the point

**Our Response Style:**
```
John -

Available times:
• Tue 10am
• Wed 2pm  
• Thu 11am

Which works?

[Name]
```

---

## Detection Algorithm

### Analyze These Signals:

| Signal | Formal | Casual | Direct |
|--------|--------|--------|--------|
| Message length | Long | Medium | Short |
| Greeting | "Dear" | "Hi/Hello" | Name only |
| Sign-off | "Best regards" | "Thanks/Best" | Name or none |
| Sentences | Complete | Complete | Fragments OK |
| Contractions | None | Some | Many |
| Emojis | Never | Rare | Sometimes |
| Exclamation points | Never | Some | Variable |

### Weight Scoring:
```python
def detect_tone(message):
    formal_score = 0
    casual_score = 0
    direct_score = 0
    
    # Length analysis
    word_count = len(message.split())
    if word_count > 100:
        formal_score += 2
    elif word_count < 30:
        direct_score += 2
    else:
        casual_score += 1
    
    # Greeting analysis
    if "dear" in message.lower():
        formal_score += 3
    elif "hey" in message.lower():
        casual_score += 3
    elif "hi" in message.lower():
        casual_score += 1
    
    # Sign-off analysis
    if "regards" in message.lower():
        formal_score += 2
    elif "thanks" in message.lower():
        casual_score += 1
    
    # Emoji analysis
    if any(c in message for c in "😊👍🙂"):
        casual_score += 2
        formal_score -= 2
    
    # Return dominant tone
    scores = {
        "formal": formal_score,
        "casual": casual_score,
        "direct": direct_score
    }
    return max(scores, key=scores.get)
```

---

## Response Guidelines

### Length Matching
- If they write 50 words, we write 40-60 words
- If they write 200 words, we write 150-250 words
- Never exceed 2x their length
- Never be less than 0.5x their length

### Timing Matching
- If they respond in 10 minutes, we aim for < 2 hours
- If they respond in 2 days, we can take 4-8 hours
- Always respond same business day if possible

### Energy Matching
- Enthusiastic → Match enthusiasm
- Reserved → Stay professional
- Urgent → Acknowledge and act fast
- Casual → Relax but stay professional

---

## Industry-Specific Adjustments

### Tech/Startups
- Default: Business Casual
- Acceptable: Casual, Direct
- Avoid: Overly Formal

### Finance/Legal
- Default: Formal Professional
- Acceptable: Business Casual
- Avoid: Casual

### Healthcare
- Default: Formal Professional
- Acceptable: Business Casual
- Avoid: Too casual, slang

### Creative/Marketing
- Default: Business Casual
- Acceptable: Casual
- Avoid: Stiff/formal

---

## Personalization Tokens

### Always Personalize:
- First name (never full name in greeting)
- Company name
- Specific pain point mentioned
- Reference to previous conversation

### Personalization Examples:

**Good:**
```
Hi Sarah, following up on our chat about your 
pipeline visibility challenges...
```

**Bad:**
```
Hi Sarah Smith from Acme Corporation, following up 
on our previous correspondence regarding your 
stated business requirements...
```

---

## Things to NEVER Do

### Language to Avoid:
- ❌ "Per my last email..."
- ❌ "As I mentioned previously..."
- ❌ "I hope this email finds you well" (with formal prospects only)
- ❌ "Just checking in..." (be specific)
- ❌ "Touch base" (be specific)
- ❌ "Circle back" (be specific)
- ❌ "Synergy" (never)
- ❌ "Low-hanging fruit" (never)

### Structural Mistakes:
- ❌ ALL CAPS (except acronyms)
- ❌ Multiple exclamation points!!!
- ❌ Walls of text (break it up)
- ❌ Too many bullet points (max 5)
- ❌ Multiple CTAs (one clear ask)

---

## Emotional Intelligence

### Reading Frustration:
**Signals:**
- Short, curt responses
- "..."  or "?" alone
- Delayed responses after quick initial exchange
- Questions that should have been answered

**Response:**
- Acknowledge any confusion
- Be extra clear and helpful
- Offer easy out if needed

### Reading Excitement:
**Signals:**
- Quick responses
- Multiple questions
- Exclamation points
- Forward-looking language

**Response:**
- Match energy
- Move quickly
- Provide next steps immediately

### Reading Hesitation:
**Signals:**
- "I need to think about it"
- "Let me check with..."
- Delayed responses
- Vague answers

**Response:**
- Don't push
- Offer to help with internal sell
- Suggest smaller commitment
- Leave door open

---

## Quality Checklist

Before sending any email, verify:

- [ ] Tone matches prospect's style
- [ ] Length is appropriate
- [ ] First name spelled correctly
- [ ] Company name spelled correctly
- [ ] One clear call-to-action
- [ ] No banned phrases
- [ ] Personalization included
- [ ] Signature appropriate for tone
- [ ] Read aloud - does it sound human?
