import streamlit as st
import sportsdataverse.mbb as mbb
import pandas as pd
import os
import warnings

warnings.simplefilter(action='ignore', category=FutureWarning)

# --- 1. PAGE SETUP ---
st.set_page_config(page_title="Rudi Madness", page_icon="🏆", layout="wide")
st.title("🏆 Live Rudi Madness Tracker")
st.markdown("Stats and eliminations automatically refresh from live 2026 tournament data.")

# --- 2. LOAD ROSTERS FROM LOCAL CSV ---
@st.cache_data(ttl=300) 
def load_rosters():
    if not os.path.exists("rosters.csv"):
        st.error("⚠️ 'rosters.csv' not found! Please create it in your VSCode folder.")
        return {}
        
    try:
        roster_df = pd.read_csv("rosters.csv")
        owner_dict = {}
        for index, row in roster_df.iterrows():
            player = str(row['Player']).strip()
            owner = str(row['Fantasy Team']).strip()
            owner_dict[player] = owner
        return owner_dict
    except Exception as e:
        st.error(f"Failed to read 'rosters.csv': {e}")
        return {}

player_to_owner = load_rosters()

# --- 3. THE AUTO-ELIMINATION ENGINE ---
@st.cache_data(ttl=120)
def get_eliminated_teams():
    try:
        team_df = mbb.load_mbb_team_boxscore(seasons=[2026], return_as_pandas=True)
        
        if 'game_date' in team_df.columns:
            team_df['game_date'] = pd.to_datetime(team_df['game_date'], utc=True, errors='coerce')
            tourney_start = pd.to_datetime('2026-03-17', utc=True)
            tourney_games = team_df[team_df['game_date'] >= tourney_start].copy()
            
            tourney_games['team_score'] = pd.to_numeric(tourney_games['team_score'], errors='coerce').fillna(0)
            tourney_games['opponent_team_score'] = pd.to_numeric(tourney_games['opponent_team_score'], errors='coerce').fillna(0)
            
            losers = tourney_games[tourney_games['team_score'] < tourney_games['opponent_team_score']]
            
            team_col = 'team_short_display_name' if 'team_short_display_name' in losers.columns else 'team_display_name'
            return losers[team_col].unique().tolist()
    except Exception as e:
        pass 
    return []

eliminated_teams = get_eliminated_teams()

# --- TEMPORARY DEBUG TEST ---
#eliminated_teams.append("Duke") 

# --- 4. PLAYER DATA ENGINE ---
@st.cache_data(ttl=60)
def pull_tournament_stats():
    try:
        df = mbb.load_mbb_player_boxscore(seasons=[2026], return_as_pandas=True)
        df = df[df['did_not_play'] == False].copy()
        
        # --- THE FIX: Memorize colleges from the regular season data ---
        team_col = 'team_short_display_name' if 'team_short_display_name' in df.columns else 'team_display_name'
        college_map = df.drop_duplicates(subset=['athlete_display_name']).set_index('athlete_display_name')[team_col].to_dict()
        
        # Now we slice the data to only include the tournament
        if 'game_date' in df.columns:
            df['game_date'] = pd.to_datetime(df['game_date'], utc=True, errors='coerce')
            cutoff_time = pd.to_datetime('2026-03-19 14:00:00', utc=True)
            df = df[df['game_date'] >= cutoff_time].copy()
        
        for col in ['points', 'rebounds', 'assists']:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            
        df['fantasy_pts'] = df['points'] + df['rebounds'] + df['assists']
        
        # Return both the live stats AND the college mapping dictionary
        return df, college_map
    except Exception as e:
        return pd.DataFrame(), {}

# Unpack both variables from the function
live_data, college_map = pull_tournament_stats()

# --- 5. PROCESSING & LEADERBOARD ---
if player_to_owner:
    roster_base = pd.DataFrame(list(player_to_owner.items()), columns=['Player', 'Fantasy Owner'])
    
    # Instantly assign colleges to everyone on your roster based on the regular season data!
    if college_map:
        roster_base['College'] = roster_base['Player'].map(college_map).fillna('Unknown College')
    else:
        roster_base['College'] = 'TBD (Awaiting Tip-off)'
    
    if not live_data.empty:
        drafted_df = live_data[live_data['athlete_display_name'].isin(player_to_owner.keys())].copy()
        
        if not drafted_df.empty:
            # We don't need to pull college from here anymore, we already have it!
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

    full_player_totals = pd.merge(roster_base, player_stats, on='Player', how='left')
    
    full_player_totals.fillna({
        'Games_Played': 0,
        'Total_Pts': 0,
        'Total_Reb': 0,
        'Total_Ast': 0,
        'Tourney_Score': 0
    }, inplace=True)

    stat_columns = ['Games_Played', 'Total_Pts', 'Total_Reb', 'Total_Ast', 'Tourney_Score']
    full_player_totals[stat_columns] = full_player_totals[stat_columns].astype(int)

    # The elimination check will now work perfectly because the College name is populated!
    full_player_totals['Status'] = full_player_totals['College'].apply(
        lambda x: "❌ Eliminated" if x in eliminated_teams else "✅ Active"
    )

    leaderboard = full_player_totals.groupby('Fantasy Owner')['Tourney_Score'].sum().reset_index()
    leaderboard = leaderboard.sort_values(by='Tourney_Score', ascending=False).reset_index(drop=True)
    leaderboard.index += 1 
    
    # --- 6. DRAW THE WEB PAGE ---
    st.header("👑 Overall Leaderboard")
    st.dataframe(
        leaderboard,
        width='stretch', 
        hide_index=False
    )
    
    
            
    st.divider()
    
    st.header("📊 Fantasy Team Rosters")
    for owner in leaderboard['Fantasy Owner']:
        with st.expander(f"View roster for {owner}"):
            
            team_slice = full_player_totals[full_player_totals['Fantasy Owner'] == owner].copy()
            team_slice = team_slice.sort_values(by=['Status', 'Tourney_Score'], ascending=[False, False])
            
            display_slice = team_slice.drop(columns=['Fantasy Owner'])
            
            def highlight_eliminated(row):
                return ['color: #ff4b4b;' if (col == 'Player' and row['Status'] == '❌ Eliminated') else '' for col in row.index]
            
            styled_slice = display_slice.style.apply(highlight_eliminated, axis=1)
            
            st.dataframe(styled_slice, width='stretch', height=480, hide_index=True) 

else:
    st.warning("Please create and save your 'rosters.csv' file to load the teams.")