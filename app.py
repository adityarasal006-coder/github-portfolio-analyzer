import streamlit as st
import requests
import os
import google.generativeai as genai
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import json
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv
from streamlit_lottie import st_lottie
from collections import Counter
import base64

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(
    page_title="GitAudit Pro: AI Recruiter",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- 2. CUSTOM CSS (Enhanced Glassmorphism & Neon) ---
st.markdown("""
    <style>
    /* Main Background */
    .stApp {
        background: radial-gradient(circle at 10% 20%, rgb(15, 20, 30) 0%, rgb(0, 0, 0) 90%);
        color: #E0E0E0;
    }
    /* Glassmorphism Cards */
    div[data-testid="stMetric"], div.stInfo, div.stSuccess, div.stWarning, div.stError {
        background: rgba(255, 255, 255, 0.05);
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        border-radius: 15px;
        border: 1px solid rgba(255, 255, 255, 0.1);
        padding: 15px;
        box-shadow: 0 4px 30px rgba(0, 0, 0, 0.5);
        transition: transform 0.3s ease;
    }
    div[data-testid="stMetric"]:hover {
        transform: translateY(-5px);
        box-shadow: 0 8px 40px rgba(0, 255, 255, 0.2);
        border-color: rgba(0, 255, 255, 0.3);
    }
    /* Neon Text */
    h1, h2, h3 {
        color: #ffffff;
        text-shadow: 0 0 10px rgba(0, 255, 255, 0.5);
    }
    /* Custom Button */
    .stButton>button {
        background: linear-gradient(45deg, #FF4B2B, #FF416C);
        color: white;
        border: none;
        border-radius: 25px;
        height: 50px;
        font-size: 18px;
        font-weight: bold;
        transition: all 0.3s ease;
        box-shadow: 0 5px 15px rgba(255, 65, 108, 0.4);
        width: 100%;
    }
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 20px rgba(255, 65, 108, 0.6);
    }
    /* Progress Bar Styling */
    .stProgress > div > div {
        background-color: #00ff00;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 3. ENHANCED HELPER FUNCTIONS ---
load_dotenv()
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")

def load_lottieurl(url: str):
    r = requests.get(url)
    if r.status_code != 200: return None
    return r.json()

def get_working_model():
    """Finds a working model."""
    if not GEMINI_KEY: return None
    try:
        genai.configure(api_key=GEMINI_KEY)
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                if 'flash' in m.name: return m.name
        return "models/gemini-1.5-flash"
    except:
        return "models/gemini-1.5-flash"

def calculate_documentation_score(repo):
    """Calculate documentation quality score"""
    score = 0
    if repo.get('readme_exists', False): score += 40
    if repo.get('description'): score += 20
    if repo.get('homepage'): score += 10
    if repo.get('has_wiki'): score += 15
    if repo.get('has_pages'): score += 15
    return min(score, 100)

def calculate_code_quality_score(repo):
    """Calculate code structure and quality score"""
    score = 0
    if repo.get('languages_count', 0) > 0: score += 20
    if repo.get('has_issues', False): score += 15
    if repo.get('has_projects', False): score += 15
    if repo.get('size', 0) > 0: score += 25
    if repo.get('stargazers_count', 0) > 0: score += 25
    return min(score, 100)

def calculate_activity_score(repo):
    """Calculate commit frequency and consistency"""
    score = 0
    pushed_at = datetime.strptime(repo.get('pushed_at', '2000-01-01'), '%Y-%m-%dT%H:%M:%SZ')
    days_since_update = (datetime.now() - pushed_at).days
    
    if days_since_update < 7: score += 40
    elif days_since_update < 30: score += 30
    elif days_since_update < 90: score += 20
    else: score += 10
    
    if repo.get('open_issues_count', 0) > 0: score += 20
    if repo.get('forks_count', 0) > 0: score += 20
    if repo.get('watchers_count', 0) > 0: score += 20
    
    return min(score, 100)

def get_readme_content(repo_full_name, headers):
    """Fetch README content for a repository"""
    try:
        readme_url = f"https://api.github.com/repos/{repo_full_name}/readme"
        response = requests.get(readme_url, headers=headers)
        if response.status_code == 200:
            content = response.json().get('content', '')
            return base64.b64decode(content).decode('utf-8')[:500]  # First 500 chars
    except:
        pass
    return None

def get_commit_activity(repo_full_name, headers):
    """Get commit activity for the last month"""
    try:
        url = f"https://api.github.com/repos/{repo_full_name}/stats/commit_activity"
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json()
    except:
        pass
    return None

def get_enhanced_github_data(username):
    """Enhanced GitHub data fetching with more metrics"""
    if not GITHUB_TOKEN: return "NO_TOKEN"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    
    try:
        # Get user data
        user_res = requests.get(f"https://api.github.com/users/{username}", headers=headers)
        if user_res.status_code != 200: return "ERROR"
        user_data = user_res.json()
        
        # Get repositories with pagination
        repos = []
        page = 1
        while len(repos) < 50:  # Get up to 50 repos
            repos_res = requests.get(
                f"https://api.github.com/users/{username}/repos?sort=updated&per_page=30&page={page}", 
                headers=headers
            )
            if repos_res.status_code != 200: break
            page_repos = repos_res.json()
            if not page_repos: break
            repos.extend(page_repos)
            page += 1
        
        # Enhance repository data
        enhanced_repos = []
        for repo in repos:
            # Check for README
            repo_full_name = repo['full_name']
            readme = get_readme_content(repo_full_name, headers)
            repo['readme_exists'] = readme is not None
            repo['readme_preview'] = readme
            
            # Get languages
            lang_url = repo['languages_url']
            lang_res = requests.get(lang_url, headers=headers)
            repo['languages'] = lang_res.json() if lang_res.status_code == 200 else {}
            repo['languages_count'] = len(repo['languages'])
            
            # Get commit activity
            commits = get_commit_activity(repo_full_name, headers)
            repo['commit_activity'] = commits
            
            # Calculate scores
            repo['doc_score'] = calculate_documentation_score(repo)
            repo['code_score'] = calculate_code_quality_score(repo)
            repo['activity_score'] = calculate_activity_score(repo)
            
            enhanced_repos.append(repo)
        
        # Get organizations
        orgs_res = requests.get(f"https://api.github.com/users/{username}/orgs", headers=headers)
        orgs = orgs_res.json() if orgs_res.status_code == 200 else []
        
        return {
            "user": user_data, 
            "repos": enhanced_repos,
            "orgs": orgs
        }
    except Exception as e:
        st.error(f"Error fetching data: {str(e)}")
        return "ERROR"

def calculate_portfolio_score(data):
    """Calculate comprehensive portfolio score"""
    if not data or data in ["ERROR", "NO_TOKEN"]:
        return 0, {}
    
    repos = data.get('repos', [])
    if not repos:
        return 0, {}
    
    # Calculate average scores
    doc_score = sum(r.get('doc_score', 0) for r in repos) / len(repos)
    code_score = sum(r.get('code_score', 0) for r in repos) / len(repos)
    activity_score = sum(r.get('activity_score', 0) for r in repos) / len(repos)
    
    # Repository organization score
    org_score = 0
    if data.get('orgs'): org_score += 20
    if len(repos) >= 5: org_score += 20
    if len(repos) >= 3: org_score += 20
    
    # Pinned repositories (if we could detect them)
    pinned_score = 30  # Default
    
    # Impact score
    total_stars = sum(r.get('stargazers_count', 0) for r in repos)
    total_forks = sum(r.get('forks_count', 0) for r in repos)
    impact_score = min(100, (total_stars * 2 + total_forks) / 5)
    
    # Technical depth score
    tech_score = 0
    languages = set()
    for repo in repos:
        languages.update(repo.get('languages', {}).keys())
    tech_score += min(40, len(languages) * 8)
    
    weights = {
        'documentation': 0.20,
        'code_quality': 0.20,
        'activity': 0.15,
        'organization': 0.15,
        'impact': 0.15,
        'technical_depth': 0.15
    }
    
    final_score = (
        doc_score * weights['documentation'] +
        code_score * weights['code_quality'] +
        activity_score * weights['activity'] +
        org_score * weights['organization'] +
        impact_score * weights['impact'] +
        tech_score * weights['technical_depth']
    )
    
    dimension_scores = {
        'Documentation Quality': round(doc_score, 1),
        'Code Structure & Best Practices': round(code_score, 1),
        'Activity Consistency': round(activity_score, 1),
        'Repository Organization': round(org_score, 1),
        'Project Impact': round(impact_score, 1),
        'Technical Depth': round(tech_score, 1)
    }
    
    return round(final_score, 1), dimension_scores

def get_actionable_recommendations(data, dimension_scores):
    """Generate specific, actionable recommendations"""
    recommendations = []
    
    if dimension_scores['Documentation Quality'] < 60:
        recommendations.append({
            'repo': 'General',
            'issue': 'Poor Documentation',
            'action': 'Add comprehensive READMEs with setup instructions, features, and screenshots',
            'priority': 'High'
        })
    
    if dimension_scores['Activity Consistency'] < 50:
        recommendations.append({
            'repo': 'General',
            'issue': 'Inconsistent Activity',
            'action': 'Commit code at least 3-4 times per week to show active development',
            'priority': 'Medium'
        })
    
    # Find repos needing improvement
    for repo in data.get('repos', []):
        if repo.get('doc_score', 0) < 40:
            recommendations.append({
                'repo': repo['name'],
                'issue': 'Missing Documentation',
                'action': f"Add a detailed README.md to {repo['name']} with project description and setup guide",
                'priority': 'High'
            })
        
        if repo.get('stargazers_count', 0) == 0 and repo.get('forks_count', 0) == 0:
            recommendations.append({
                'repo': repo['name'],
                'issue': 'Low Impact',
                'action': f"Promote {repo['name']} on social media and add screenshots to attract users",
                'priority': 'Medium'
            })
    
    return recommendations[:5]  # Return top 5

def analyze_with_ai(data, model_name):
    """Enhanced AI analysis with more metrics"""
    if not model_name: return None
    model = genai.GenerativeModel(model_name, generation_config={"temperature": 0.2})
    
    repo_summary = [f"{r['name']} ({r.get('language','N/A')}) - ⭐{r.get('stargazers_count',0)}" for r in data['repos'][:10]]
    langs = list(set([r.get('language') for r in data['repos'] if r.get('language')]))
    
    prompt = f"""
    Act as a VP of Engineering at a top tech company. Analyze this GitHub profile thoroughly.
    
    USER PROFILE:
    Username: {data['user']['login']}
    Name: {data['user'].get('name', 'N/A')}
    Bio: {data['user'].get('bio', 'None')}
    Location: {data['user'].get('location', 'N/A')}
    Followers: {data['user']['followers']}
    Following: {data['user']['following']}
    Public Repos: {data['user']['public_repos']}
    Account Created: {data['user']['created_at'][:10]}
    
    TOP REPOSITORIES (with stars):
    {chr(10).join(repo_summary)}
    
    LANGUAGES USED: {', '.join(langs) if langs else 'None'}
    
    ORGANIZATIONS: {len(data.get('orgs', []))}
    
    Based on this data, provide a detailed JSON analysis with:
    1. Overall score (0-100)
    2. Verdict (Hire/Strong Consider/Interview/Cultivate/Pass)
    3. Best fitting job role
    4. Executive summary
    5. Technical skills with proficiency scores
    6. Soft skills assessment
    7. Top 5 strengths
    8. Top 5 red flags
    9. 5 specific interview questions based on their actual projects
    10. 3 repos to archive (with reasons)
    11. 3 repos to improve (with specific improvements)
    
    RETURN STRICT JSON (No Markdown):
    {{
        "score": 0,
        "verdict": "Verdict",
        "role": "Best Fitting Role",
        "summary": "Executive summary here",
        "skills": {{"Python": 90, "React": 80}},
        "soft_skills": {{"Communication": 70, "Leadership": 60}},
        "pros": ["strength1", "strength2", "strength3", "strength4", "strength5"],
        "cons": ["redflag1", "redflag2", "redflag3", "redflag4", "redflag5"],
        "interview_questions": ["Q1 based on their projects", "Q2", "Q3", "Q4", "Q5"],
        "archive_repos": [{{"name": "repo1", "reason": "why to archive"}}],
        "improve_repos": [{{"name": "repo2", "improvement": "specific improvement"}}]
    }}
    """
    
    try:
        response = model.generate_content(prompt)
        text = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except Exception as e:
        st.error(f"AI Analysis Error: {str(e)}")
        return None

# --- 4. UI LAYOUT ---
st.title("⚡ GitAudit **Ultra**")
st.markdown("##### AI-Powered Technical Recruiter & Portfolio Analyzer")

# Input Section with Enhanced UI
c1, c2, c3 = st.columns([3, 1, 1])
with c1:
    username = st.text_input("GitHub Username", placeholder="e.g. octocat", key="username_input")
with c2:
    st.write("##")
    analyze_btn = st.button("🚀 ANALYZE PROFILE", use_container_width=True)
with c3:
    st.write("##")
    if st.button("🎯 SAMPLE DEMO", use_container_width=True):
        username = "torvalds"  # Demo with Linus Torvalds

# Load animation
lottie_scanning = load_lottieurl("https://assets9.lottiefiles.com/packages/lf20_w51pcehl.json")

if analyze_btn:
    if not username:
        st.warning("Please enter a GitHub username!")
    else:
        # Animation
        if lottie_scanning:
            st_lottie(lottie_scanning, height=200, key="scanning")
        
        with st.spinner("🔍 Scanning GitHub repositories... Analyzing code quality..."):
            time.sleep(1)
            
            # Get enhanced data
            data = get_enhanced_github_data(username)
            
            if data == "ERROR":
                st.error("❌ User not found or API rate limit exceeded. Please try again later.")
            elif data == "NO_TOKEN":
                st.error("⚠️ GitHub Token not configured. Please check your .env file.")
            else:
                # Calculate portfolio score
                portfolio_score, dimension_scores = calculate_portfolio_score(data)
                
                # Get AI analysis
                model = get_working_model()
                ai_result = analyze_with_ai(data, model)
                
                # Get actionable recommendations
                recommendations = get_actionable_recommendations(data, dimension_scores)
                
                # Success animation
                st.balloons()
                st.success(f"✅ Analysis complete for @{username}")
                
                # --- MAIN DASHBOARD ---
                
                # Top Metrics Row
                col1, col2, col3, col4, col5 = st.columns(5)
                
                with col1:
                    st.metric("📊 Portfolio Score", f"{portfolio_score}/100", 
                             delta="Top 10%" if portfolio_score > 80 else None)
                
                with col2:
                    st.metric("📚 Total Repos", data['user']['public_repos'])
                
                with col3:
                    total_stars = sum(r.get('stargazers_count', 0) for r in data['repos'])
                    st.metric("⭐ Total Stars", total_stars)
                
                with col4:
                    st.metric("👥 Followers", data['user']['followers'])
                
                with col5:
                    if ai_result:
                        st.metric("🎯 AI Verdict", ai_result['verdict'])
                
                st.markdown("---")
                
                # Tabbed Interface
                tab1, tab2, tab3, tab4 = st.tabs([
                    "📈 Portfolio Overview", 
                    "🔍 Repository Analysis", 
                    "💡 Recommendations",
                    "🎤 Interview Prep"
                ])
                
                with tab1:
                    # Portfolio Overview Tab
                    col_left, col_right = st.columns([2, 1])
                    
                    with col_left:
                        st.subheader("🎯 Dimension-wise Scores")
                        
                        # Create radar chart for dimensions
                        fig = go.Figure(data=go.Scatterpolar(
                            r=list(dimension_scores.values()),
                            theta=list(dimension_scores.keys()),
                            fill='toself',
                            marker=dict(color='rgba(0, 255, 255, 0.8)')
                        ))
                        fig.update_layout(
                            polar=dict(
                                radialaxis=dict(
                                    visible=True,
                                    range=[0, 100]
                                )),
                            showlegend=False,
                            paper_bgcolor="rgba(0,0,0,0)",
                            font_color="white"
                        )
                        st.plotly_chart(fig, use_container_width=True)
                    
                    with col_right:
                        st.subheader("📊 Language Distribution")
                        all_langs = []
                        for repo in data['repos']:
                            all_langs.extend(repo.get('languages', {}).keys())
                        
                        if all_langs:
                            lang_counts = Counter(all_langs)
                            df_langs = pd.DataFrame(
                                list(lang_counts.items()), 
                                columns=['Language', 'Count']
                            ).head(8)
                            
                            fig = px.pie(
                                df_langs, 
                                values='Count', 
                                names='Language',
                                color_discrete_sequence=px.colors.qualitative.Set3,
                                hole=0.4
                            )
                            fig.update_layout(
                                paper_bgcolor="rgba(0,0,0,0)",
                                font_color="white"
                            )
                            st.plotly_chart(fig, use_container_width=True)
                    
                    # Profile Summary
                    st.subheader("📋 Profile Summary")
                    if ai_result:
                        st.info(ai_result['summary'])
                    
                    # Activity Timeline
                    st.subheader("📅 Recent Activity")
                    repo_updates = []
                    for repo in data['repos'][:10]:
                        pushed_at = datetime.strptime(repo['pushed_at'], '%Y-%m-%dT%H:%M:%SZ')
                        repo_updates.append({
                            'Repository': repo['name'],
                            'Last Updated': pushed_at,
                            'Stars': repo['stargazers_count']
                        })
                    
                    df_activity = pd.DataFrame(repo_updates)
                    df_activity = df_activity.sort_values('Last Updated', ascending=False)
                    
                    fig = px.bar(
                        df_activity, 
                        x='Repository', 
                        y='Stars',
                        title='Repository Stars',
                        color='Stars',
                        color_continuous_scale='Viridis'
                    )
                    fig.update_layout(
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                        font_color="white"
                    )
                    st.plotly_chart(fig, use_container_width=True)
                
                with tab2:
                    # Repository Analysis Tab
                    st.subheader("📁 Repository Deep Dive")
                    
                    # Repository selector
                    repo_names = [r['name'] for r in data['repos']]
                    selected_repo = st.selectbox("Select Repository to Analyze", repo_names)
                    
                    if selected_repo:
                        repo = next(r for r in data['repos'] if r['name'] == selected_repo)
                        
                        col1, col2, col3 = st.columns(3)
                        col1.metric("📝 Documentation", f"{repo['doc_score']}/100")
                        col2.metric("💻 Code Quality", f"{repo['code_score']}/100")
                        col3.metric("⚡ Activity", f"{repo['activity_score']}/100")
                        
                        # Repository details
                        st.write("---")
                        col_left, col_right = st.columns(2)
                        
                        with col_left:
                            st.write("**Repository Stats**")
                            st.write(f"- ⭐ Stars: {repo['stargazers_count']}")
                            st.write(f"- 🔱 Forks: {repo['forks_count']}")
                            st.write(f"- 🐛 Open Issues: {repo['open_issues_count']}")
                            st.write(f"- 📏 Size: {repo['size']} KB")
                            st.write(f"- 📅 Created: {repo['created_at'][:10]}")
                            st.write(f"- 🔄 Last Updated: {repo['pushed_at'][:10]}")
                        
                        with col_right:
                            if repo.get('languages'):
                                st.write("**Languages Used**")
                                lang_df = pd.DataFrame(
                                    list(repo['languages'].items()), 
                                    columns=['Language', 'Bytes']
                                )
                                fig = px.pie(
                                    lang_df, 
                                    values='Bytes', 
                                    names='Language',
                                    hole=0.3
                                )
                                fig.update_layout(
                                    paper_bgcolor="rgba(0,0,0,0)",
                                    font_color="white",
                                    height=300
                                )
                                st.plotly_chart(fig, use_container_width=True)
                        
                        # README Preview
                        if repo.get('readme_preview'):
                            st.write("**README Preview**")
                            st.text(repo['readme_preview'][:300] + "...")
                        else:
                            st.warning("⚠️ No README found for this repository")
                
                with tab3:
                    # Recommendations Tab
                    st.subheader("💡 Actionable Recommendations")
                    
                    # Display AI recommendations if available
                    if ai_result and 'improve_repos' in ai_result:
                        st.write("### 📌 Top Repositories to Improve")
                        for item in ai_result['improve_repos'][:3]:
                            with st.expander(f"🔧 {item['name']}"):
                                st.write(item['improvement'])
                    
                    if ai_result and 'archive_repos' in ai_result:
                        st.write("### 🗑️ Repositories to Consider Archiving")
                        for item in ai_result['archive_repos'][:3]:
                            with st.expander(f"📦 {item['name']}"):
                                st.write(item['reason'])
                    
                    # Display metric-based recommendations
                    st.write("### 🎯 Priority Improvements")
                    for i, rec in enumerate(recommendations[:3], 1):
                        with st.container():
                            st.markdown(f"""
                            **{i}. {rec['repo']}** - *{rec['issue']}*
                            - 🔹 **Action:** {rec['action']}
                            - ⚡ **Priority:** {rec['priority']}
                            ---
                            """)
                    
                    # General advice
                    st.write("### 📈 Recruiter's Perspective")
                    st.info("""
                    **What recruiters look for:**
                    1. **Clean, well-documented code** - Shows professionalism
                    2. **Consistent commit history** - Demonstrates dedication
                    3. **Diverse tech stack** - Indicates adaptability
                    4. **Project completeness** - Proves ability to ship
                    5. **Community engagement** - Shows collaboration skills
                    """)
                
                with tab4:
                    # Interview Prep Tab
                    if ai_result and 'interview_questions' in ai_result:
                        st.subheader("🎤 Technical Interview Questions")
                        st.write("Based on the candidate's actual projects:")
                        
                        for i, q in enumerate(ai_result['interview_questions'], 1):
                            with st.expander(f"Question {i}"):
                                st.write(q)
                        
                        st.subheader("🧠 Skills Assessment")
                        
                        # Skills display
                        if 'skills' in ai_result:
                            col1, col2 = st.columns(2)
                            
                            with col1:
                                st.write("**Technical Skills**")
                                skills_df = pd.DataFrame(
                                    list(ai_result['skills'].items()),
                                    columns=['Skill', 'Proficiency']
                                )
                                fig = px.bar(
                                    skills_df,
                                    x='Proficiency',
                                    y='Skill',
                                    orientation='h',
                                    color='Proficiency',
                                    color_continuous_scale='Viridis'
                                )
                                fig.update_layout(
                                    paper_bgcolor="rgba(0,0,0,0)",
                                    plot_bgcolor="rgba(0,0,0,0)",
                                    font_color="white",
                                    height=300
                                )
                                st.plotly_chart(fig, use_container_width=True)
                            
                            with col2:
                                if 'soft_skills' in ai_result:
                                    st.write("**Soft Skills**")
                                    soft_df = pd.DataFrame(
                                        list(ai_result['soft_skills'].items()),
                                        columns=['Skill', 'Proficiency']
                                    )
                                    fig = px.bar(
                                        soft_df,
                                        x='Proficiency',
                                        y='Skill',
                                        orientation='h',
                                        color='Proficiency',
                                        color_continuous_scale='Plasma'
                                    )
                                    fig.update_layout(
                                        paper_bgcolor="rgba(0,0,0,0)",
                                        plot_bgcolor="rgba(0,0,0,0)",
                                        font_color="white",
                                        height=300
                                    )
                                    st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.warning("Interview questions could not be generated. Please try again.")
                
                # Footer with key insights
                st.markdown("---")
                st.subheader("🎯 Key Takeaways")
                
                col1, col2 = st.columns(2)
                with col1:
                    if ai_result:
                        st.success("✅ **Top Strengths**")
                        for p in ai_result['pros'][:3]:
                            st.write(f"• {p}")
                
                with col2:
                    if ai_result:
                        st.error("🚩 **Areas for Improvement**")
                        for c in ai_result['cons'][:3]:
                            st.write(f"• {c}")
                
                # Export functionality
                st.markdown("---")
                if st.button("📥 Export Analysis Report"):
                    # Create report data
                    report = {
                        'username': username,
                        'portfolio_score': portfolio_score,
                        'dimension_scores': dimension_scores,
                        'ai_analysis': ai_result,
                        'repositories': [
                            {
                                'name': r['name'],
                                'stars': r['stargazers_count'],
                                'forks': r['forks_count'],
                                'doc_score': r['doc_score']
                            } for r in data['repos'][:10]
                        ]
                    }
                    
                    # Convert to JSON and offer download
                    report_json = json.dumps(report, indent=2)
                    st.download_button(
                        label="⬇️ Download JSON Report",
                        data=report_json,
                        file_name=f"github_audit_{username}.json",
                        mime="application/json"
                    )