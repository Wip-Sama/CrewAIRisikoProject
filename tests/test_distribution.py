import math

def test_distribution(num_territories, limit):
    my_territory_names = [f"T{i}" for i in range(num_territories)]
    
    if limit <= 0 or limit >= num_territories:
        print(f"Default: {len(my_territory_names)} agents")
        return
    
    chunk_size = num_territories // limit
    remainder = num_territories % limit
    
    agents = []
    start_idx = 0
    for i in range(limit):
        current_chunk_size = chunk_size + (1 if i < remainder else 0)
        end_idx = start_idx + current_chunk_size
        agent_territories = my_territory_names[start_idx:end_idx]
        agents.append(agent_territories)
        start_idx = end_idx
        
    for i, a in enumerate(agents):
        print(f"Agent {i+1}: {len(a)} territories ({a[0]}...{a[-1]})")

print("--- 21 territories, 5 agents ---")
test_distribution(21, 5)
print("\n--- 42 territories, 6 agents ---")
test_distribution(42, 6)
print("\n--- 10 territories, 3 agents ---")
test_distribution(10, 3)
