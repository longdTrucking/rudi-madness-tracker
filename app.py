import streamlit as st
import pandas as pd
import requests
import os
import warnings
import time

# Ignore Pandas future warnings to keep the terminal clean
warnings.simplefilter(action='ignore', category=FutureWarning)

# --- GLOBAL CONFIGURATION ---
# Dates for Round 1 through the National Championship (Skips the First Four)
TOURNEY_DATES = [
    '20260319', '20260320', '20260321', '20260322', 
    '20260326', '20260327', '20260328', '20260329', 
    '20260404', '20260406'
]

# --- 1. PAGE SETUP ---
st.set_page_config(page_title="Rudi Madness", page_icon="🏆", layout="wide")
st.title("🏆 Live Rudi Madness Tracker")
st.markdown("Stats and eliminations automatically refresh directly from the live ESPN scoreboard.")

# --- 2. DATA LOADERS ---

@st.cache_data(ttl=300) 
def load_rosters():
    """Loads the fantasy league rosters from a local CSV file."""
    if not os.path.exists("rosters.csv"):
        st.error("⚠️ 'rosters.csv' not found! Please create it in your VSCode folder.")
        return pd.DataFrame()
        
    try:
        df = pd.read_csv("rosters.csv")
        # Standardize column name
        if 'Fantasy Team' in df.columns:
            df = df.rename(columns={'Fantasy Team': 'Fantasy Owner'})
        # Strip invisible whitespace to prevent matching errors
        df['Player'] = df['Player'].astype(str).str.strip()
        return df
    except Exception as e:
        st.error(f"Failed to read 'rosters.csv': {e}")
        return pd.DataFrame()

@st.cache_data(ttl=86400) 
def build_college_dictionary():
    """Builds a Player-to-College mapping using the sportsdataverse historical database. Runs once a day."""
    try:
        import sportsdataverse.mbb as mbb
        df = mbb.load_mbb_player_boxscore(seasons=[2026], return_as_pandas=True)
        
        # Isolate just the player names and their teams, removing all duplicate game logs
        mapping_df = df[['athlete_display_name', 'team_short_display_name']].drop_duplicates(subset=['athlete_display_name'])
        
        # Convert to a fast Python dictionary
        return dict(zip(mapping_df.athlete_display_name, mapping_df.team_short_display_name))
    except Exception as e:
        print(f"Failed to build college dictionary: {e}")
        return {}

# --- 3. ESPN LIVE DATA ENGINES ---

@st.cache_data(ttl=120)
def get_eliminated_teams():
    """Scrapes the live ESPN scoreboard to find teams that have officially lost."""
    eliminated = []
    
    for date_str in TOURNEY_DATES:
        url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard?dates={date_str}"
        try:
            data = requests.get(url).json()
            for event in data.get('events', []):
                comp = event['competitions'][0]
                
                # Check if the game is completely finished
                if comp['status']['type']['completed']: 
                    for team in comp['competitors']:
                        # If winner flag is False, the team is eliminated
                        if team.get('winner') == False:
                            eliminated.append(team['team']['displayName'])
                            eliminated.append(team['team']['shortDisplayName']) 
        except:
            continue
            
    return list(set(eliminated))

@st.cache_data(ttl=60)
def pull_tournament_stats():
    """Scrapes the live ESPN box scores to calculate fantasy points for all active players."""
    all_player_stats = []
    
    for date_str in TOURNEY_DATES:
        schedule_url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard?dates={date_str}"
        try:
            sched_data = requests.get(schedule_url).json()
            events = sched_data.get('events', [])
            
            for game in events:
                status = game['competitions'][0]['status']['type']['description']
                
                # Only pull stats if the game has actually tipped off
                if status != "Scheduled":
                    game_id = game['id']
                    summary_url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/summary?event={game_id}"
                    
                    try:
                        summary_data = requests.get(summary_url).json()
                        if 'boxscore' in summary_data and 'players' in summary_data['boxscore']:
                            for team in summary_data['boxscore']['players']:
                                # Skip teams that haven't registered any stats yet
                                if not team.get('statistics'):
                                    continue
                                    
                                labels = team['statistics'][0]['labels']
                                pts_idx = labels.index('PTS') if 'PTS' in labels else -1
                                reb_idx = labels.index('REB') if 'REB' in labels else -1
                                ast_idx = labels.index('AST') if 'AST' in labels else -1
                                
                                for athlete in team['statistics'][0]['athletes']:
                                    name = athlete['athlete']['displayName']
                                    stats = athlete.get('stats')
                                    
                                    if stats and pts_idx != -1:
                                        try:
                                            pts = int(stats[pts_idx])
                                            reb = int(stats[reb_idx])
                                            ast = int(stats[ast_idx])
                                        except ValueError:
                                            pts, reb, ast = 0, 0, 0
                                            
                                        all_player_stats.append({
                                            'athlete_display_name': name,
                                            'points': pts,
                                            'rebounds': reb,
                                            'assists': ast,
                                            'fantasy_pts': pts + reb + ast,
                                            'game_id': game_id
                                        })
                    except:
                        continue
        except:
            continue
            
    if all_player_stats:
        return pd.DataFrame(all_player_stats)
    else:
        return pd.DataFrame(columns=['athlete_display_name', 'points', 'rebounds', 'assists', 'fantasy_pts', 'game_id'])

# --- 4. EXECUTE DATA FETCHING ---
roster_base = load_rosters()
college_map = build_college_dictionary()
eliminated_teams = get_eliminated_teams()
live_data = pull_tournament_stats()

# Apply the automated colleges to the CSV roster
if not roster_base.empty:
    roster_base['College'] = roster_base['Player'].map(college_map).fillna('Unknown College')

# --- 5. DATA MERGING & MATH ---
if not roster_base.empty:
    
    # Calculate total points per player
    if not live_data.empty:
        drafted_df = live_data[live_data['athlete_display_name'].isin(roster_base['Player'])].copy()
        
        if not drafted_df.empty:
            player_stats = drafted_df.groupby('athlete_display_name').agg(
                Games_Played=('game_id', 'nunique'),
                Total_Pts=('points', 'sum'),
                Total_Reb=('rebounds', 'sum'),
                Total_Ast=('assists', 'sum'),
                Tourney_Score=('fantasy_pts', 'sum')
            ).reset_index()
            player_stats = player_stats.rename(columns={'athlete_display_name': 'Player'})
        else:
            player_stats = pd.DataFrame(columns=['Player', 'Games_Played', 'Total_Pts', 'Total_Reb', 'Total_Ast', 'Tourney_Score'])
    else:
        player_stats = pd.DataFrame(columns=['Player', 'Games_Played', 'Total_Pts', 'Total_Reb', 'Total_Ast', 'Tourney_Score'])

    # Merge stats back onto the main roster
    full_player_totals = pd.merge(roster_base, player_stats, on='Player', how='left')
    
    full_player_totals.fillna({
        'Games_Played': 0, 'Total_Pts': 0, 'Total_Reb': 0, 'Total_Ast': 0, 'Tourney_Score': 0
    }, inplace=True)

    stat_columns = ['Games_Played', 'Total_Pts', 'Total_Reb', 'Total_Ast', 'Tourney_Score']
    full_player_totals[stat_columns] = full_player_totals[stat_columns].astype(int)

    # Check eliminations against the automatically assigned college
    full_player_totals['Status'] = full_player_totals['College'].apply(
        lambda x: "❌ Eliminated" if x in eliminated_teams else "✅ Active"
    )

    # Calculate Overall Leaderboard
    leaderboard = full_player_totals.groupby('Fantasy Owner')['Tourney_Score'].sum().reset_index()
    leaderboard = leaderboard.sort_values(by='Tourney_Score', ascending=False).reset_index(drop=True)
    
    # Format the Leaderboard
    leaderboard.insert(0, 'Rank', range(1, len(leaderboard) + 1))
    leaderboard = leaderboard.rename(columns={'Fantasy Owner': 'Manager', 'Tourney_Score': 'Total Points'})

    # --- 6. DRAW THE WEB PAGE ---
    st.header("👑 Overall Leaderboard")
    
    # Float the leaderboard in the center using columns
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.dataframe(
            leaderboard,
            hide_index=True,
            use_container_width=True
        )
            
    st.divider()
    
    st.header("📊 Fantasy Team Rosters")
    for owner in leaderboard['Manager']:
        
        # Isolate the roster for the specific manager
        team_slice = full_player_totals[full_player_totals['Fantasy Owner'] == owner].copy()
        
        total_players = len(team_slice)
        active_players = len(team_slice[team_slice['Status'] == '✅ Active'])
        
        # Build the interactive expander
        with st.expander(f"View roster for {owner} ({active_players}/{total_players} Active)"):
            
            # Sort: Active on top, then rank by Points
            team_slice = team_slice.sort_values(by=['Status', 'Tourney_Score'], ascending=[True, False])
            display_slice = team_slice.drop(columns=['Fantasy Owner'])
            
            # Highlight eliminated rows in red
            def highlight_eliminated(row):
                return ['color: #ff4b4b;' if (col == 'Player' and row['Status'] == '❌ Eliminated') else '' for col in row.index]
            
            styled_slice = display_slice.style.apply(highlight_eliminated, axis=1)
            st.dataframe(styled_slice, width='stretch', height=480, hide_index=True) 

else:
    st.warning("Please create your 'rosters.csv' file with Player and Fantasy Team columns.")

# --- 7. AUTO-REFRESH ENGINE ---
# Automatically reloads the page every 60 seconds to pull live data without manual refreshing
#time.sleep(60)
#st.rerun()