import pexpect, time, chess, os, datetime

ENGINE_PATHS = {
    "Engine A": "",
    "Engine B": ""
}

def start_engine(engine_path: str, name: str = "Engine") -> pexpect.spawn:
    try:
        engine = pexpect.spawn(engine_path, encoding='utf-8', timeout=None)
        engine.sendline("uci")
        engine.expect("uciok", timeout=120)
        if name == "Engine A":
          contempt_value = globals().get("match_config", {}).get("contemptA", None)
        else:
           contempt_value = globals().get("match_config", {}).get("contemptB", None)
        if contempt_value is not None:
            engine.sendline(f"setoption name Contempt value {contempt_value}")
        engine.sendline("isready")
        engine.expect("readyok", timeout=120)
        print(f"{name} iniciado e pronto.")
        return engine
    except (pexpect.exceptions.TIMEOUT, Exception) as e:
        print(f"ERRO ao iniciar '{name}' ({engine_path}): {e}")
        raise

def get_engine_move_data(engine: pexpect.spawn, fen: str, wtime_ms: int, btime_ms: int, winc_ms: int, binc_ms: int, engine_name: str = "Engine") -> tuple[str, int | None, int | None, float | None, int | None, float]:
    """Retorna: best_move, depth, nodes, nps, score_cp, score_mate, time_taken_ms"""
    engine.sendline(f"position fen {fen}")
    engine.sendline(f"go wtime {wtime_ms} btime {btime_ms} winc {winc_ms} binc {binc_ms}")
    
    best_move, depth, nodes, score_cp, score_mate = None, None, None, None, None
    start_time = time.monotonic() # Tempo de início para calcular time_taken_ms
    
    while True:
        try:
            line = engine.readline().strip()
            if not line: continue
            
            if "info" in line:
                parts = line.split()
                try:
                    if "depth" in parts:
                        depth = int(parts[parts.index("depth") + 1])
                    if "nodes" in parts:
                        nodes = int(parts[parts.index("nodes") + 1])
                    if "score" in parts:
                        stype = parts[parts.index("score") + 1]
                        sval = int(parts[parts.index("score") + 2])
                        if stype == "cp":
                            score_cp = sval / 100.0
                            score_mate = None
                        elif stype == "mate":
                            score_mate = sval
                            score_cp = None
                except (ValueError, IndexError):
                    pass

            if line.startswith("bestmove"):
                best_move = line.split()[1]
                break
        except (pexpect.exceptions.TIMEOUT, Exception) as e:
            print(f"[{engine_name}] ERRO ao ler saída da engine: {e}")
            best_move = "resign"
            break
            
    time_taken_ms = (time.monotonic() - start_time) * 1000 # Tempo total gasto na busca
    nps = nodes / (time_taken_ms / 1000.0) if nodes and time_taken_ms > 0 else 0

    return best_move, depth, nodes, nps, score_cp, score_mate, time_taken_ms

def apply_move(board: chess.Board, move_uci: str):
    board.push_uci(move_uci)

def run_chess_match(engine1_name: str, engine1_path: str, engine2_name: str, engine2_path: str, config: dict):
    print(f"===== INICIANDO PARTIDA ENTRE {engine1_name.upper()} E {engine2_name.upper()} =====")
    
    engine1_proc, engine2_proc = None, None
    board = chess.Board(config.get('initial_fen', chess.STARTING_FEN))
    moves_played = 0
    game_pgn = ""
    game_result = "*"

    time_left_engine1 = config.get('timelimit_ms', 600000)
    time_left_engine2 = config.get('timelimit_ms', 600000)
    
    try:
        engine1_proc = start_engine(engine1_path, engine1_name)
        engine2_proc = start_engine(engine2_path, engine2_name)
        
        while not board.is_game_over() and moves_played < config.get('num_moves', 50):
            current_turn_is_white = (board.turn == chess.WHITE)
            current_engine_name = engine1_name if current_turn_is_white else engine2_name
            current_engine_proc = engine1_proc if current_turn_is_white else engine2_proc
            
            print(f"\n--- Turno {board.fullmove_number}: {'Brancas' if current_turn_is_white else 'Pretas'} ({current_engine_name}) ---")
            print("Tabuleiro atual:\n", board)
            
            # Captura o tempo restante atual antes da busca
            current_time_before_search = time.monotonic()

            best_move_uci, depth, nodes, nps, score_cp, score_mate, time_spent_ms = get_engine_move_data(
                current_engine_proc,
                board.fen(),
                time_left_engine1,
                time_left_engine2,
                config.get('increment_ms', 100),
                config.get('increment_ms', 100),
                current_engine_name
            )

            # Atualiza o tempo restante da engine
            if current_turn_is_white:
                time_left_engine1 -= time_spent_ms
                time_left_engine1 += config.get('increment_ms', 100)
            else:
                time_left_engine2 -= time_spent_ms
                time_left_engine2 += config.get('increment_ms', 100)
            
            if not best_move_uci or best_move_uci == "resign":
                print(f"[{current_engine_name}] desistiu ou não encontrou jogada.")
                game_result = "0-1" if current_turn_is_white else "1-0"
                break

            try:
                move = chess.Move.from_uci(best_move_uci)
                if move not in board.legal_moves:
                    raise ValueError(f"Jogada ilegal retornada: {best_move_uci}")
                
                move_san = board.san(move)
                apply_move(board, best_move_uci)
            
            except ValueError as e:
                print(f"[{current_engine_name}] ERRO: {e}. Partida encerrada.")
                game_result = "0-1" if current_turn_is_white else "1-0"
                break
            
            score_str = f"({score_cp:.2f} CP)" if score_cp is not None else (f"(Mate em {score_mate})" if score_mate is not None else "")
            
            remaining_time_str = f"Tempo Restante: Brancas {time_left_engine1 / 1000:.1f}s, Pretas {time_left_engine2 / 1000:.1f}s"
            depth_str = f", Profundidade: {depth}" if depth is not None else ""
            nps_str = f", NPS: {nps:,.0f} 🚀" if nps is not None else ""
            
            print(f"[{current_engine_name}] jogou: {move_san} ({best_move_uci}) {score_str}{depth_str}{nps_str}")
            print(remaining_time_str)

            if current_turn_is_white:
                game_pgn += f"{board.fullmove_number}. {move_san} "
            else:
                game_pgn += f"{move_san} "
            
            moves_played += 1
            
        if board.is_game_over() and game_result == "*":
            game_result = board.result()

        print(f"\n===== PARTIDA ENCERRADA! =====")
        print(f"Resultado final: {game_result}")
        print(f"PGN da partida:\n\n{game_pgn.strip()}\n")

    except Exception as e:
        print(f"\nERRO FATAL INESPERADO: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("\n--- Finalizando engines ---")
        for proc, name in [(engine1_proc, engine1_name), (engine2_proc, engine2_name)]:
            if proc and proc.isalive():
                try:
                    proc.sendline("quit")
                    proc.close()
                    print(f"{name} encerrado.")
                except:
                    pass

if __name__ == "__main__":
    match_config = {
        'hash_size': 246,
        'threads': 1,
        'timelimit_ms': 9000,
        'increment_ms': 675,
        'num_moves': 1000,
        'initial_fen': "",
        'contemptA': 20,
        'contemptB': 0
    }

    run_chess_match(
        "", ENGINE_PATHS["Engine A"],
        "", ENGINE_PATHS["Engine B"],
        match_config
    )
                            
