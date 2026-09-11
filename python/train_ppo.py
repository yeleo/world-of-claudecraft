"""PPO (Proximal Policy Optimization) training script for World of ClaudeCraft RL agent.

Utilizes Gymnasium AsyncVectorEnv for multi-environment parallel sampling and
GPU (CUDA) acceleration for policy/value network optimization.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections import deque

import numpy as np

# Ensure claudecraft conda env bin (with node) is in PATH
CONDA_PREFIX = os.environ.get("CONDA_PREFIX", "/home/yeleo/miniconda3/envs/claudecraft")
NODE_BIN = os.path.join(CONDA_PREFIX, "bin")
if NODE_BIN not in os.environ.get("PATH", ""):
    os.environ["PATH"] = f"{NODE_BIN}:{os.environ.get('PATH', '')}"

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import gymnasium as gym
import torch
import torch.nn as nn
import torch.optim as optim
from torch.distributions.categorical import Categorical

from wow_env import WoWClassicEnv, make_env


class ActorCritic(nn.Module):
    """Actor-Critic MLP network with shared feature extraction."""

    def __init__(self, obs_dim: int, act_dim: int) -> None:
        super().__init__()
        self.shared = nn.Sequential(
            nn.Linear(obs_dim, 512),
            nn.Tanh(),
            nn.Linear(512, 256),
            nn.Tanh(),
        )
        self.actor = nn.Linear(256, act_dim)
        self.critic = nn.Linear(256, 1)

        # Orthogonal initialization
        for m in self.modules():
            if isinstance(m, nn.Linear):
                nn.init.orthogonal_(m.weight, gain=np.sqrt(2))
                nn.init.constant_(m.bias, 0.0)
        nn.init.orthogonal_(self.actor.weight, gain=0.01)
        nn.init.orthogonal_(self.critic.weight, gain=1.0)

    def get_action_and_value(self, x: torch.Tensor, action: torch.Tensor | None = None):
        features = self.shared(x)
        logits = self.actor(features)
        dist = Categorical(logits=logits)
        if action is None:
            action = dist.sample()
        return action, dist.log_prob(action), dist.entropy(), self.critic(features)

    def get_value(self, x: torch.Tensor) -> torch.Tensor:
        return self.critic(self.shared(x))


def parse_args():
    parser = argparse.ArgumentParser(description="World of ClaudeCraft PPO Training")
    parser.add_argument("--total-timesteps", type=int, default=3_000_000, help="Total environment steps")
    parser.add_argument("--num-envs", type=int, default=8, help="Number of parallel environments")
    parser.add_argument("--num-steps", type=int, default=256, help="Steps per rollout per env")
    parser.add_argument("--lr", type=float, default=3e-4, help="Learning rate")
    parser.add_argument("--gamma", type=float, default=0.99, help="Discount factor")
    parser.add_argument("--gae-lambda", type=float, default=0.95, help="GAE lambda parameter")
    parser.add_argument("--clip-coef", type=float, default=0.2, help="PPO surrogate clip ratio")
    parser.add_argument("--ent-coef", type=float, default=0.01, help="Entropy bonus coefficient")
    parser.add_argument("--vf-coef", type=float, default=0.5, help="Value function loss coefficient")
    parser.add_argument("--max-grad-norm", type=float, default=0.5, help="Max gradient norm clipping")
    parser.add_argument("--update-epochs", type=int, default=4, help="PPO update epochs per rollout")
    parser.add_argument("--num-minibatches", type=int, default=4, help="Minibatches per update")
    parser.add_argument("--save-interval", type=int, default=500_000, help="Timesteps interval to save checkpoint")
    parser.add_argument("--player-class", type=str, default="warrior", help="Player class for the agent")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--models-dir", type=str, default=os.path.join(_HERE, "models"), help="Output directory")
    return parser.parse_args()


def main():
    args = parse_args()
    os.makedirs(args.models_dir, exist_ok=True)

    # Set seeds
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"==================================================")
    print(f" World of ClaudeCraft - PPO Training")
    print(f" Target Steps : {args.total_timesteps:,}")
    print(f" Parallel Envs: {args.num_envs}")
    print(f" Device       : {device} ({torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU'})")
    print(f" Class        : {args.player_class}")
    print(f" Checkpoint   : Every {args.save_interval:,} steps")
    print(f" Output Dir   : {args.models_dir}")
    print(f"==================================================")

    # Instantiate parallel vector environments
    env_fns = [make_env(player_class=args.player_class) for _ in range(args.num_envs)]
    envs = gym.vector.AsyncVectorEnv(env_fns)

    obs_dim = envs.single_observation_space.shape[0]
    act_dim = envs.single_action_space.n
    print(f"Obs Dimension : {obs_dim}, Action Space: {act_dim}")

    agent = ActorCritic(obs_dim, act_dim).to(device)
    optimizer = optim.Adam(agent.parameters(), lr=args.lr, eps=1e-5)

    # Storage buffers
    obs_buf = torch.zeros((args.num_steps, args.num_envs, obs_dim), device=device)
    actions_buf = torch.zeros((args.num_steps, args.num_envs), device=device)
    logprobs_buf = torch.zeros((args.num_steps, args.num_envs), device=device)
    rewards_buf = torch.zeros((args.num_steps, args.num_envs), device=device)
    dones_buf = torch.zeros((args.num_steps, args.num_envs), device=device)
    values_buf = torch.zeros((args.num_steps, args.num_envs), device=device)

    # Tracking metrics
    ep_rewards_history = deque(maxlen=50)
    ep_lens_history = deque(maxlen=50)
    current_ep_rewards = np.zeros(args.num_envs)
    current_ep_lens = np.zeros(args.num_envs)

    batch_size = args.num_envs * args.num_steps
    minibatch_size = batch_size // args.num_minibatches
    num_updates = args.total_timesteps // batch_size

    # Reset environments
    next_obs, _ = envs.reset(seed=args.seed)
    next_obs = torch.as_tensor(next_obs, dtype=torch.float32, device=device)
    next_done = torch.zeros(args.num_envs, device=device)

    global_step = 0
    start_time = time.time()
    last_save_step = 0

    print("Starting training loop...\n")

    for update in range(1, num_updates + 1):
        # Rollout collection
        for step in range(args.num_steps):
            global_step += args.num_envs
            obs_buf[step] = next_obs
            dones_buf[step] = next_done

            with torch.no_grad():
                action, logprob, _, value = agent.get_action_and_value(next_obs)
                values_buf[step] = value.flatten()
            actions_buf[step] = action
            logprobs_buf[step] = logprob

            # Step in environment
            cpu_actions = action.cpu().numpy()
            step_obs, rewards, terminations, truncations, infos = envs.step(cpu_actions)

            rewards_buf[step] = torch.as_tensor(rewards, dtype=torch.float32, device=device)
            dones = np.logical_or(terminations, truncations)

            current_ep_rewards += rewards
            current_ep_lens += 1

            for idx, done_flag in enumerate(dones):
                if done_flag:
                    ep_rewards_history.append(current_ep_rewards[idx])
                    ep_lens_history.append(current_ep_lens[idx])
                    current_ep_rewards[idx] = 0.0
                    current_ep_lens[idx] = 0

            next_obs = torch.as_tensor(step_obs, dtype=torch.float32, device=device)
            next_done = torch.as_tensor(dones, dtype=torch.float32, device=device)

        # Compute Generalized Advantage Estimation (GAE)
        with torch.no_grad():
            next_value = agent.get_value(next_obs).reshape(1, -1)
            advantages = torch.zeros_like(rewards_buf, device=device)
            lastgaelam = 0
            for t in reversed(range(args.num_steps)):
                if t == args.num_steps - 1:
                    nextnonterminal = 1.0 - next_done
                    nextvalues = next_value
                else:
                    nextnonterminal = 1.0 - dones_buf[t + 1]
                    nextvalues = values_buf[t + 1]
                delta = rewards_buf[t] + args.gamma * nextvalues * nextnonterminal - values_buf[t]
                advantages[t] = lastgaelam = delta + args.gamma * args.gae_lambda * nextnonterminal * lastgaelam
            returns = advantages + values_buf

        # Flatten rollout buffers
        b_obs = obs_buf.reshape(-1, obs_dim)
        b_logprobs = logprobs_buf.reshape(-1)
        b_actions = actions_buf.reshape(-1)
        b_advantages = advantages.reshape(-1)
        b_returns = returns.reshape(-1)
        b_values = values_buf.reshape(-1)

        # Normalize advantages
        b_advantages = (b_advantages - b_advantages.mean()) / (b_advantages.std() + 1e-8)

        # PPO optimization epochs
        b_inds = np.arange(batch_size)
        clipfracs = []
        for _ in range(args.update_epochs):
            np.random.shuffle(b_inds)
            for start in range(0, batch_size, minibatch_size):
                end = start + minibatch_size
                mb_inds = b_inds[start:end]

                _, newlogprob, entropy, newvalue = agent.get_action_and_value(b_obs[mb_inds], b_actions[mb_inds].long())
                logratio = newlogprob - b_logprobs[mb_inds]
                ratio = logratio.exp()

                with torch.no_grad():
                    clipfracs.append(((ratio - 1.0).abs() > args.clip_coef).float().mean().item())

                # Policy loss
                pg_loss1 = -b_advantages[mb_inds] * ratio
                pg_loss2 = -b_advantages[mb_inds] * torch.clamp(ratio, 1 - args.clip_coef, 1 + args.clip_coef)
                pg_loss = torch.max(pg_loss1, pg_loss2).mean()

                # Value loss (clipped)
                newvalue = newvalue.view(-1)
                v_loss_unclipped = (newvalue - b_returns[mb_inds]) ** 2
                v_clipped = b_values[mb_inds] + torch.clamp(newvalue - b_values[mb_inds], -args.clip_coef, args.clip_coef)
                v_loss_clipped = (v_clipped - b_returns[mb_inds]) ** 2
                v_loss = 0.5 * torch.max(v_loss_unclipped, v_loss_clipped).mean()

                # Entropy loss
                entropy_loss = entropy.mean()

                loss = pg_loss - args.ent_coef * entropy_loss + args.vf_coef * v_loss

                optimizer.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_(agent.parameters(), args.max_grad_norm)
                optimizer.step()

        # Telemetry logging
        elapsed = time.time() - start_time
        fps = int(global_step / max(1e-5, elapsed))
        if update % 5 == 0 or update == 1 or update == num_updates:
            avg_rew = np.mean(ep_rewards_history) if ep_rewards_history else 0.0
            avg_len = np.mean(ep_lens_history) if ep_lens_history else 0.0
            progress = (global_step / args.total_timesteps) * 100
            print(
                f"[{progress:5.1f}%] Step: {global_step:9,}/{args.total_timesteps:,} | "
                f"FPS: {fps:4d} | "
                f"Avg Reward: {avg_rew:7.2f} | "
                f"Avg Len: {avg_len:5.1f} | "
                f"Policy Loss: {pg_loss.item():.4f} | "
                f"Value Loss: {v_loss.item():.4f}"
            )

        # Periodic checkpoint
        if global_step - last_save_step >= args.save_interval or global_step >= args.total_timesteps:
            ckpt_path = os.path.join(args.models_dir, f"woc_ppo_step_{global_step}.pth")
            torch.save({
                "global_step": global_step,
                "model_state_dict": agent.state_dict(),
                "obs_dim": obs_dim,
                "act_dim": act_dim,
                "player_class": args.player_class,
            }, ckpt_path)
            print(f"  >>> Checkpoint saved to: {ckpt_path}")
            last_save_step = global_step

    # Save final model
    final_path = os.path.join(args.models_dir, "woc_policy_3m.pth")
    torch.save({
        "global_step": global_step,
        "model_state_dict": agent.state_dict(),
        "obs_dim": obs_dim,
        "act_dim": act_dim,
        "player_class": args.player_class,
    }, final_path)
    print(f"\n==================================================")
    print(f" Training complete in {elapsed / 60:.1f} minutes!")
    print(f" Final Model Saved: {final_path}")
    print(f"==================================================")

    envs.close()


if __name__ == "__main__":
    main()
