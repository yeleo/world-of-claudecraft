// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { setLanguage } from '../src/ui/i18n';
import { NPCS } from '../src/sim/data';
import { QuestDialogController } from '../src/ui/hud/quest/quest_dialog_controller';
import { MarketWindow } from '../src/ui/market_window';
import type { Entity } from '../src/sim/types';

describe('Market dialog open flow', () => {
  beforeEach(() => {
    setLanguage('zh_CN');
    document.body.innerHTML = `
      <div id="quest-dialog" class="window panel ui-window" style="display:none"></div>
      <div id="market-window" class="window panel ui-window" style="display:none"></div>
      <div id="bags" class="window panel ui-window" style="display:none"></div>
      <div id="ui"></div>
    `;
  });

  it('completes NPC dialog to market window open with zero exceptions', () => {
    const marketEl = document.getElementById('market-window')!;
    const questDialogEl = document.getElementById('quest-dialog')!;
    expect(marketEl).not.toBeNull();
    expect(questDialogEl).not.toBeNull();

    const merchantDef = NPCS['the_merchant'];
    expect(merchantDef).toBeDefined();
    expect(merchantDef.market).toBe(true);

    const npcEntity: Entity = {
      id: 99,
      kind: 'npc',
      templateId: 'the_merchant',
      name: 'The Merchant',
      pos: { x: 10, y: 0, z: 10 },
      rot: 0,
      radius: 1,
      maxHp: 100,
      hp: 100,
      level: 10,
      dead: false,
      questIds: [],
      vendorItems: [],
    } as any;

    const playerEntity: Entity = {
      id: 1,
      kind: 'player',
      name: 'Hero',
      pos: { x: 11, y: 0, z: 10 },
      rot: 0,
      radius: 1,
      maxHp: 100,
      hp: 100,
      level: 10,
      dead: false,
    } as any;

    const entitiesMap = new Map<number, Entity>();
    entitiesMap.set(npcEntity.id, npcEntity);
    entitiesMap.set(playerEntity.id, playerEntity);

    const mockWorld = {
      player: playerEntity,
      cfg: { playerClass: 'warrior' },
      entities: entitiesMap,
      marketInfo: null,
      inventory: [],
      questLog: new Map(),
      questState: () => 'none',
      convertHusks: vi.fn(),
      marketSearch: vi.fn(),
      marketSellPriceCheck: vi.fn(),
      stationPlacements: [],
      craftingIdentity: { craftSkills: [], attunedPairs: [] },
    };

    let marketWindow: MarketWindow;
    const deps: any = {
      element: questDialogEl,
      document,
      world: () => mockWorld,
      now: () => Date.now(),
      text: {
        npcName: (id: string) => NPCS[id]?.name ?? id,
        mobName: (id: string) => id,
        npcTitle: () => 'Merchant',
        npcGreeting: () => 'Welcome!',
        delveName: () => '',
        questTitle: () => '',
        questNarrative: () => '',
        objectiveLabel: () => '',
        number: (n: number) => String(n),
        progress: () => '',
        suggestedPlayers: () => '',
        money: (c: number) => `${c}c`,
      },
      openFocusTrap: () => ({
        opener: () => document.body,
        release: vi.fn(),
        focusFirst: vi.fn(),
      }),
      closeTransient: vi.fn(),
      hideTooltip: vi.fn(),
      itemIcon: () => '',
      itemTooltip: () => '',
      attachTooltip: vi.fn(),
      openChronicles: vi.fn(),
      openVendor: vi.fn(),
      openHeroicVendor: vi.fn(),
      openCrucibleVendor: vi.fn(),
      openWarfareVendor: vi.fn(),
      openTrain: vi.fn(),
      openUnbind: vi.fn(),
      openCrafting: vi.fn(),
      openMarket: () => {
        console.log('openMarket triggered!');
        marketWindow.open();
      },
      openDelveBoard: vi.fn(),
      openCardDuel: vi.fn(),
      onOpenChange: vi.fn(),
      voice: { play: vi.fn(), isPlaying: () => false, setDistance: vi.fn() },
    };

    const dialogController = new QuestDialogController(deps);

    marketWindow = new MarketWindow({
      itemIcon: () => '<span>icon</span>',
      moneyHtml: (c: number) => `${c}c`,
      itemTooltip: () => '',
      attachTooltip: vi.fn(),
      root: () => marketEl,
      world: () => mockWorld as any,
      closeOthers: vi.fn(),
      hideTooltip: vi.fn(),
      captureFocus: () => null,
      restoreFocus: vi.fn(),
      showError: vi.fn(),
      slotName: () => 'bag',
      syncBags: vi.fn(),
      confirmDialog: vi.fn(),
    });

    console.log('1. Opening NPC dialog...');
    dialogController.open(npcEntity.id);
    expect(questDialogEl.style.display).toBe('block');

    const marketBtn = questDialogEl.querySelector<HTMLButtonElement>('[data-market]');
    console.log('2. Market button found:', !!marketBtn, 'Text:', marketBtn?.textContent);
    expect(marketBtn).not.toBeNull();

    console.log('3. Clicking market button...');
    marketBtn!.click();

    console.log('4. Market display after click:', marketEl.style.display);
    expect(marketEl.style.display).toBe('flex');
    expect(marketWindow.isOpen).toBe(true);
    expect(document.body.classList.contains('market-open')).toBe(true);

    // Now test slowHud tick check:
    console.log('5. Checking nearbyMarketNpc simulation...');
    const nearbyMarketNpc = () => {
      const p = mockWorld.player;
      for (const e of mockWorld.entities.values()) {
        if (
          e.kind === 'npc' &&
          NPCS[e.templateId]?.market &&
          Math.hypot(p.pos.x - e.pos.x, p.pos.z - e.pos.z) <= 8
        ) {
          return e;
        }
      }
      return null;
    };
    expect(nearbyMarketNpc()).not.toBeNull();

    // Now simulate marketInfo arriving from server:
    console.log('6. Simulating marketInfo update...');
    mockWorld.marketInfo = {
      listings: [
        {
          id: 1,
          sellerName: 'Voss',
          itemId: 'copper_ore',
          count: 20,
          price: 100,
          mine: false,
          house: false,
        },
      ],
      totalCount: 1,
      filter: '',
      itemType: 'all',
      subtype: 'all',
      armorClass: 'all',
      primaryStat: 'all',
      rarity: 'all',
      sort: 'name',
      collapseLowest: false,
      page: 0,
      pageCount: 1,
      collectionCopper: 0,
      collectionItems: [],
      collectionSales: [],
      collectionSalesOmitted: 0,
      cutPct: 5,
      maxListings: 12,
      myListingCount: 0,
      sellPriceItemId: null,
      sellLowestPrice: null,
      sweepQuote: null,
    } as any;

    marketWindow.refreshIfChanged();
    console.log('7. Market refreshed with listing. Rows count:', marketEl.querySelectorAll('.mkt-row').length);
    expect(marketEl.querySelectorAll('.mkt-row').length).toBe(1);
  });
});
