#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");
const { spawn } = require("child_process");

const {
  Accessory,
  Categories,
  Characteristic,
  HAPStorage,
  Service,
  uuid,
} = require("hap-nodejs");

const ROOT_DIR = __dirname;
const PYTHON = path.join(ROOT_DIR, ".venv", "bin", "python");
const MAIN = path.join(ROOT_DIR, "main.py");
const RUNTIME_DIR = path.join(ROOT_DIR, ".homekit");
const STORAGE_DIR = path.join(RUNTIME_DIR, "persist");
const STATE_PATH = path.join(RUNTIME_DIR, "state.json");
const LOG_PATH = path.join(ROOT_DIR, "logs", "homekit_bridge.log");

function loadRuntimeConfig() {
  const configPath = path.resolve(process.env.MITSUBRIDGE_CONFIG || path.join(ROOT_DIR, "config.json"));
  if (!fs.existsSync(configPath)) {
    return {};
  }

  try {
    return JSON.parse(fs.readFileSync(configPath, "utf8"));
  } catch (error) {
    throw new Error(`Invalid MitsuBridge config ${configPath}: ${error.message}`);
  }
}

function configValue(envName, configObject, key, fallback) {
  const envValue = process.env[envName];
  if (envValue !== undefined && envValue !== "") {
    return envValue;
  }
  const configObjectValue = configObject && configObject[key];
  if (configObjectValue !== undefined && configObjectValue !== "") {
    return configObjectValue;
  }
  return fallback;
}

function configBoolean(envName, configObject, key, fallback) {
  const envValue = process.env[envName];
  if (envValue !== undefined && envValue !== "") {
    return ["1", "true", "yes", "on"].includes(envValue.toLowerCase());
  }
  const configObjectValue = configObject && configObject[key];
  if (configObjectValue !== undefined) {
    return Boolean(configObjectValue);
  }
  return fallback;
}

const RUNTIME_CONFIG = loadRuntimeConfig();
const HOMEKIT_CONFIG = RUNTIME_CONFIG.homekit || {};

const ACCESSORY_NAME = configValue("MITSUBRIDGE_HOMEKIT_NAME", HOMEKIT_CONFIG, "name", "Mitsubishi AC");
const USERNAME = configValue("MITSUBRIDGE_HOMEKIT_USERNAME", HOMEKIT_CONFIG, "username", "4A:4D:52:40:AC:02");
const PIN_CODE = configValue("MITSUBRIDGE_HOMEKIT_PIN", HOMEKIT_CONFIG, "pin", "031-45-154");
const SETUP_ID = configValue("MITSUBRIDGE_HOMEKIT_SETUP_ID", HOMEKIT_CONFIG, "setup_id", "MI02");
const PORT = Number(configValue("MITSUBRIDGE_HOMEKIT_PORT", HOMEKIT_CONFIG, "port", "51827"));
const DEFAULT_TARGET_TEMPERATURE = 25.0;
const DEFAULT_MODE = "cooling";
const DEFAULT_FAN_SPEED = "auto";
const TEMPERATURE_MIN = 23.5;
const TEMPERATURE_MAX = 28.0;
const EXPOSE_COMMAND_SWITCHES = configBoolean(
  "MITSUBRIDGE_HOMEKIT_SWITCHES",
  HOMEKIT_CONFIG,
  "expose_command_switches",
  false,
);

const MODE_ACTIONS = new Map([
  ["auto", "mode_auto"],
  ["cooling", "mode_cooling"],
  ["heat", "mode_heat"],
  ["fan", "mode_fan"],
  ["dry", "mode_dry"],
]);
const MODE_BY_ACTION = new Map(
  [...MODE_ACTIONS.entries()].map(([mode, action]) => [action, mode]),
);

const FAN_ACTIONS = new Map([
  ["auto", "fan_auto"],
  ["low", "fan_low"],
  ["medium", "fan_medium"],
  ["high", "fan_high"],
]);
const FAN_BY_ACTION = new Map(
  [...FAN_ACTIONS.entries()].map(([speed, action]) => [action, speed]),
);
const FAN_SPEED_VALUES = {
  auto: 0,
  low: 33,
  medium: 66,
  high: 100,
};
const MODE_LABELS = {
  auto: "自动",
  cooling: "制冷",
  heat: "制热",
  fan: "送风",
  dry: "除湿",
};
const FAN_LABELS = {
  auto: "自动",
  low: "低",
  medium: "中",
  high: "高",
};

const TEMPERATURE_ACTIONS = new Map([
  [23.5, "temp_235"],
  [24.0, "temp_240"],
  [24.5, "temp_245"],
  [25.0, "temp_250"],
  [25.5, "temp_255"],
  [26.0, "temp_260"],
  [26.5, "temp_265"],
  [27.0, "temp_270"],
  [27.5, "temp_275"],
  [28.0, "temp_280"],
]);
const TEMPERATURE_BY_ACTION = new Map(
  [...TEMPERATURE_ACTIONS.entries()].map(([temperature, action]) => [action, temperature]),
);

const ACTION_LABELS = {
  on: "开机",
  off: "关机",
  mode_auto: "自动模式",
  mode_cooling: "制冷模式",
  mode_heat: "制热模式",
  mode_fan: "送风模式",
  mode_dry: "除湿模式",
  cooling: "制冷 25度",
  heat: "制热模式",
  dry: "除湿模式",
  fan: "送风模式",
  fan_auto: "自动风量",
  fan_low: "低风量",
  fan_medium: "中风量",
  fan_high: "高风量",
  temp_235: "温度 23.5度",
  temp_240: "温度 24度",
  temp_245: "温度 24.5度",
  temp_250: "温度 25度",
  temp_255: "温度 25.5度",
  temp_260: "温度 26度",
  temp_265: "温度 26.5度",
  temp_270: "温度 27度",
  temp_275: "温度 27.5度",
  temp_280: "温度 28度",
};

const DEFAULT_STATE = {
  active: false,
  mode: "off",
  targetTemperature: DEFAULT_TARGET_TEMPERATURE,
  fanSpeed: DEFAULT_FAN_SPEED,
  busy: false,
  lastAction: null,
  lastFeedback: null,
  lastError: null,
  updatedAt: null,
};

fs.mkdirSync(STORAGE_DIR, { recursive: true });
fs.mkdirSync(path.dirname(LOG_PATH), { recursive: true });
HAPStorage.setCustomStoragePath(STORAGE_DIR);

function now() {
  return new Date().toISOString();
}

function log(message) {
  const line = `[${now()}] ${message}`;
  console.log(line);
  fs.appendFileSync(LOG_PATH, `${line}\n`);
}

function readState() {
  try {
    return { ...DEFAULT_STATE, ...JSON.parse(fs.readFileSync(STATE_PATH, "utf8")) };
  } catch {
    return { ...DEFAULT_STATE };
  }
}

let state = readState();

function writeState(patch = {}) {
  state = {
    ...state,
    ...patch,
    updatedAt: now(),
  };
  fs.writeFileSync(STATE_PATH, `${JSON.stringify(state, null, 2)}\n`);
  refreshHomeKitState();
}

function temperatureActionFor(value) {
  const requested = Number(value);
  if (!Number.isFinite(requested)) {
    return null;
  }

  const rounded = Math.round(requested * 2) / 2;
  for (const [temperature, action] of TEMPERATURE_ACTIONS.entries()) {
    if (Math.abs(temperature - rounded) < 0.01) {
      return { temperature, action };
    }
  }
  return null;
}

function actionsWithPower(actions) {
  if (state.active) {
    return actions;
  }
  return ["on", ...actions];
}

function actionsForMode(mode) {
  const action = MODE_ACTIONS.get(mode);
  if (!action) {
    return [];
  }
  return actionsWithPower([action]);
}

function actionsForFanSpeed(speed) {
  const action = FAN_ACTIONS.get(speed);
  if (!action) {
    return [];
  }
  return actionsWithPower([action]);
}

function formatTemperature(value) {
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

function statePatchForAction(action, baseState) {
  if (TEMPERATURE_BY_ACTION.has(action)) {
    return {
      active: true,
      targetTemperature: TEMPERATURE_BY_ACTION.get(action),
    };
  }

  if (MODE_BY_ACTION.has(action)) {
    const mode = MODE_BY_ACTION.get(action);
    return {
      active: true,
      mode,
      targetTemperature: DEFAULT_TARGET_TEMPERATURE,
      fanSpeed: mode === "auto" ? "auto" : baseState.fanSpeed,
    };
  }

  if (FAN_BY_ACTION.has(action)) {
    return {
      active: true,
      fanSpeed: FAN_BY_ACTION.get(action),
    };
  }

  if (action === "off") {
    return { active: false, mode: "off" };
  }

  if (action === "on" || action === "cooling") {
    return {
      active: true,
      mode: DEFAULT_MODE,
      targetTemperature: DEFAULT_TARGET_TEMPERATURE,
      fanSpeed: action === "on" ? DEFAULT_FAN_SPEED : baseState.fanSpeed,
    };
  }

  if (action === "heat") {
    return { active: true, mode: "heat", targetTemperature: DEFAULT_TARGET_TEMPERATURE };
  }

  if (action === "dry") {
    return { active: true, mode: "dry" };
  }

  if (action === "fan") {
    return { active: true, mode: "fan" };
  }

  if (action === "fan_low") {
    return { active: true, fanSpeed: "low" };
  }

  return {};
}

function statePatchForActions(actions) {
  let predicted = { ...state };
  for (const action of actions) {
    predicted = {
      ...predicted,
      ...statePatchForAction(action, predicted),
    };
  }

  return {
    active: predicted.active,
    mode: predicted.mode,
    targetTemperature: predicted.targetTemperature,
    fanSpeed: predicted.fanSpeed,
  };
}

function feedbackForActions(actions) {
  const meaningful = [...actions].reverse().find((action) => action !== "on") || actions[actions.length - 1];

  if (meaningful === "off") {
    return `${ACCESSORY_NAME}已关闭`;
  }

  if (meaningful === "on") {
    return `${ACCESSORY_NAME}已开机`;
  }

  if (TEMPERATURE_BY_ACTION.has(meaningful)) {
    return `${ACCESSORY_NAME}温度已设为${formatTemperature(TEMPERATURE_BY_ACTION.get(meaningful))}度`;
  }

  if (MODE_BY_ACTION.has(meaningful)) {
    return `${ACCESSORY_NAME}已设为${MODE_LABELS[MODE_BY_ACTION.get(meaningful)]}模式`;
  }

  if (FAN_BY_ACTION.has(meaningful)) {
    return `${ACCESSORY_NAME}风量已设为${FAN_LABELS[FAN_BY_ACTION.get(meaningful)]}`;
  }

  return `${ACCESSORY_NAME}状态已更新`;
}

let actionQueue = Promise.resolve();
let pendingSignature = null;
let pendingSignatureAt = 0;

function queueActions(actions, reason) {
  const filtered = actions.filter(Boolean);
  if (!filtered.length) {
    return;
  }

  const signature = filtered.join(",");
  const timestamp = Date.now();
  if (signature === pendingSignature && timestamp - pendingSignatureAt < 2000) {
    log(`Skip duplicate HomeKit request within 2s: ${signature} reason=${reason}`);
    return;
  }

  pendingSignature = signature;
  pendingSignatureAt = timestamp;
  const targetPatch = statePatchForActions(filtered);
  const feedback = feedbackForActions(filtered);
  const lastAction = filtered[filtered.length - 1] || null;

  actionQueue = actionQueue
    .then(async () => {
      writeState({ ...targetPatch, busy: true, lastAction, lastFeedback: feedback, lastError: null });
      log(`Queue start: ${signature} reason=${reason}`);
      log(`Siri feedback pending: ${feedback}`);
      for (const action of filtered) {
        await runAction(action, reason);
      }
      writeState({ ...targetPatch, busy: false, lastAction, lastFeedback: feedback, lastError: null });
      log(`Queue done: ${signature}`);
      log(`Siri feedback confirmed: ${feedback}`);
    })
    .catch((error) => {
      const errorMessage = String(error && error.message ? error.message : error);
      writeState({ busy: false, lastAction, lastFeedback: feedback, lastError: `${feedback}失败：${errorMessage}` });
      log(`Queue failed: ${signature} error=${error && error.stack ? error.stack : error}`);
      log(`Siri feedback failed: ${feedback}`);
    });
}

function runAction(action, reason) {
  return new Promise((resolve, reject) => {
    if (!ACTION_LABELS[action]) {
      reject(new Error(`Unsupported action: ${action}`));
      return;
    }

    log(`BLE action start: ${action} (${ACTION_LABELS[action]}) reason=${reason}`);

    const child = spawn(PYTHON, [MAIN, action], {
      cwd: ROOT_DIR,
      env: { ...process.env, PYTHONUNBUFFERED: "1" },
    });

    child.stdout.on("data", (chunk) => {
      fs.appendFileSync(LOG_PATH, chunk);
    });

    child.stderr.on("data", (chunk) => {
      fs.appendFileSync(LOG_PATH, chunk);
    });

    child.on("error", (error) => {
      reject(error);
    });

    child.on("close", (code, signal) => {
      if (code === 0) {
        log(`BLE action ok: ${action}`);
        resolve();
      } else {
        reject(new Error(`Action ${action} exited with code=${code} signal=${signal || ""}`));
      }
    });
  });
}

const accessoryUuid = uuid.generate("mitsubridge:homekit:par40maac:bedroom");
const accessory = new Accessory(ACCESSORY_NAME, accessoryUuid);
accessory.category = Categories.AIR_CONDITIONER;

accessory
  .getService(Service.AccessoryInformation)
  .setCharacteristic(Characteristic.Manufacturer, "MitsuBridge")
  .setCharacteristic(Characteristic.Model, "PAR-40MAAC BLE Bridge")
  .setCharacteristic(Characteristic.SerialNumber, "MITSUBRIDGE-PAR40MAAC")
  .setCharacteristic(Characteristic.FirmwareRevision, "1.0.0")
  .setCharacteristic(Characteristic.Name, ACCESSORY_NAME);

accessory.on("identify", (_paired, callback) => {
  log("Identify requested");
  callback();
});

const climateService = accessory.addService(Service.HeaterCooler, ACCESSORY_NAME);
climateService.setPrimaryService();

function currentHeaterCoolerState() {
  if (!state.active || state.mode === "off") {
    return Characteristic.CurrentHeaterCoolerState.INACTIVE;
  }
  if (state.mode === "heat") {
    return Characteristic.CurrentHeaterCoolerState.HEATING;
  }
  return Characteristic.CurrentHeaterCoolerState.COOLING;
}

function targetHeaterCoolerState() {
  if (state.mode === "heat") {
    return Characteristic.TargetHeaterCoolerState.HEAT;
  }
  if (state.mode === "cooling") {
    return Characteristic.TargetHeaterCoolerState.COOL;
  }
  return Characteristic.TargetHeaterCoolerState.AUTO;
}

function syncTemperatureCharacteristics() {
  climateService.updateCharacteristic(Characteristic.CurrentTemperature, state.targetTemperature);
  climateService.updateCharacteristic(Characteristic.CoolingThresholdTemperature, state.targetTemperature);
  climateService.updateCharacteristic(Characteristic.HeatingThresholdTemperature, state.targetTemperature);
}

function queueTemperatureFromHomeKit(value, reason) {
  const target = temperatureActionFor(value);
  if (!target) {
    log(`Unsupported target temperature ${value}; keeping ${state.targetTemperature}`);
    syncTemperatureCharacteristics();
    return;
  }

  queueActions(actionsWithPower([target.action]), reason);
}

climateService
  .getCharacteristic(Characteristic.Active)
  .onGet(() => (state.active ? Characteristic.Active.ACTIVE : Characteristic.Active.INACTIVE))
  .onSet((value) => {
    if (value === Characteristic.Active.ACTIVE) {
      queueActions(actionsWithPower([]), "HomeKit Active=ACTIVE");
    } else {
      queueActions(["off"], "HomeKit Active=INACTIVE");
    }
  });

climateService
  .getCharacteristic(Characteristic.CurrentHeaterCoolerState)
  .onGet(currentHeaterCoolerState);

climateService
  .getCharacteristic(Characteristic.TargetHeaterCoolerState)
  .setProps({
    validValues: [
      Characteristic.TargetHeaterCoolerState.AUTO,
      Characteristic.TargetHeaterCoolerState.HEAT,
      Characteristic.TargetHeaterCoolerState.COOL,
    ],
  })
  .onGet(targetHeaterCoolerState)
  .onSet((value) => {
    if (value === Characteristic.TargetHeaterCoolerState.HEAT) {
      queueActions(actionsForMode("heat"), "HomeKit TargetHeaterCoolerState=HEAT");
    } else if (value === Characteristic.TargetHeaterCoolerState.COOL) {
      queueActions(actionsForMode("cooling"), "HomeKit TargetHeaterCoolerState=COOL");
    } else if (value === Characteristic.TargetHeaterCoolerState.AUTO) {
      queueActions(actionsForMode("auto"), "HomeKit TargetHeaterCoolerState=AUTO");
    }
  });

climateService
  .getCharacteristic(Characteristic.CurrentTemperature)
  .updateValue(state.targetTemperature)
  .setProps({ minValue: 0, maxValue: 50, minStep: 0.5 })
  .onGet(() => state.targetTemperature);

climateService
  .getCharacteristic(Characteristic.CoolingThresholdTemperature)
  .updateValue(DEFAULT_TARGET_TEMPERATURE)
  .setProps({ minValue: TEMPERATURE_MIN, maxValue: TEMPERATURE_MAX, minStep: 0.5 })
  .updateValue(state.targetTemperature)
  .onGet(() => state.targetTemperature)
  .onSet((value) => queueTemperatureFromHomeKit(value, `HomeKit CoolingThresholdTemperature=${value}`));

climateService
  .getCharacteristic(Characteristic.HeatingThresholdTemperature)
  .updateValue(DEFAULT_TARGET_TEMPERATURE)
  .setProps({ minValue: TEMPERATURE_MIN, maxValue: TEMPERATURE_MAX, minStep: 0.5 })
  .updateValue(state.targetTemperature)
  .onGet(() => state.targetTemperature)
  .onSet((value) => queueTemperatureFromHomeKit(value, `HomeKit HeatingThresholdTemperature=${value}`));

climateService
  .getCharacteristic(Characteristic.TemperatureDisplayUnits)
  .onGet(() => Characteristic.TemperatureDisplayUnits.CELSIUS)
  .onSet(() => {
    climateService.updateCharacteristic(
      Characteristic.TemperatureDisplayUnits,
      Characteristic.TemperatureDisplayUnits.CELSIUS,
    );
  });

function fanSpeedFromRotation(value) {
  const requested = Number(value);
  if (!Number.isFinite(requested) || requested <= 10) return "auto";
  if (requested <= 45) return "low";
  if (requested <= 80) return "medium";
  return "high";
}

climateService
  .getCharacteristic(Characteristic.RotationSpeed)
  .setProps({ minValue: 0, maxValue: 100, minStep: 1 })
  .onGet(() => FAN_SPEED_VALUES[state.fanSpeed] ?? FAN_SPEED_VALUES.auto)
  .onSet((value) => {
    const speed = fanSpeedFromRotation(value);
    queueActions(actionsForFanSpeed(speed), `HomeKit RotationSpeed=${value} -> ${speed}`);
  });

function addCommandSwitch(name, action, options = {}) {
  const service = accessory.addService(Service.Switch, name, name);
  service
    .getCharacteristic(Characteristic.On)
    .onGet(() => {
      if (options.reflectState === "power") return state.active;
      if (options.reflectState && options.reflectState.startsWith("mode:")) {
        return state.mode === options.reflectState.slice("mode:".length);
      }
      if (options.reflectState && options.reflectState.startsWith("fan:")) {
        return state.fanSpeed === options.reflectState.slice("fan:".length);
      }
      return false;
    })
    .onSet((value) => {
      if (!value) {
        if (options.offAction) queueActions([options.offAction], `HomeKit switch ${name}=OFF`);
        return;
      }

      const actions = typeof action === "function" ? action() : action;
      if (Array.isArray(actions)) {
        queueActions(actions, `HomeKit switch ${name}=ON`);
      } else {
        queueActions([actions], `HomeKit switch ${name}=ON`);
      }
    });
  return service;
}

if (EXPOSE_COMMAND_SWITCHES) {
  addCommandSwitch("电源", ["on"], { reflectState: "power", offAction: "off" });
  addCommandSwitch("自动模式", () => actionsForMode("auto"), { reflectState: "mode:auto" });
  addCommandSwitch("制冷模式", () => actionsForMode("cooling"), { reflectState: "mode:cooling" });
  addCommandSwitch("制热模式", () => actionsForMode("heat"), { reflectState: "mode:heat" });
  addCommandSwitch("除湿模式", () => actionsForMode("dry"), { reflectState: "mode:dry" });
  addCommandSwitch("送风模式", () => actionsForMode("fan"), { reflectState: "mode:fan" });
  addCommandSwitch("自动风量", () => actionsForFanSpeed("auto"), { reflectState: "fan:auto" });
  addCommandSwitch("低风量", () => actionsForFanSpeed("low"), { reflectState: "fan:low" });
  addCommandSwitch("中风量", () => actionsForFanSpeed("medium"), { reflectState: "fan:medium" });
  addCommandSwitch("高风量", () => actionsForFanSpeed("high"), { reflectState: "fan:high" });
}

function refreshHomeKitState() {
  if (!climateService) return;

  climateService.updateCharacteristic(
    Characteristic.Active,
    state.active ? Characteristic.Active.ACTIVE : Characteristic.Active.INACTIVE,
  );
  climateService.updateCharacteristic(Characteristic.CurrentHeaterCoolerState, currentHeaterCoolerState());
  climateService.updateCharacteristic(Characteristic.TargetHeaterCoolerState, targetHeaterCoolerState());
  syncTemperatureCharacteristics();
  climateService.updateCharacteristic(
    Characteristic.RotationSpeed,
    FAN_SPEED_VALUES[state.fanSpeed] ?? FAN_SPEED_VALUES.auto,
  );
}

refreshHomeKitState();

accessory.publish({
  username: USERNAME,
  pincode: PIN_CODE,
  port: PORT,
  category: Categories.AIR_CONDITIONER,
  setupID: SETUP_ID,
  bind: ["en1", "0.0.0.0"],
  advertiser: "ciao",
  addIdentifyingMaterial: false,
});

log(`${ACCESSORY_NAME} HomeKit bridge started`);
log(`Pairing code: ${PIN_CODE}`);
log(`Setup URI: ${accessory.setupURI()}`);
log(`Port: ${PORT}`);
log(
  `HomeKit profile: air conditioner; command switches ${EXPOSE_COMMAND_SWITCHES ? "enabled" : "disabled"}`,
);
log("Safe commands: power on/off; modes auto/cooling/heat/fan/dry; temps 23.5-28.0; fan auto/low/medium/high");

process.on("SIGINT", () => {
  log("SIGINT received, unpublishing HomeKit bridge");
  accessory.unpublish();
  process.exit(0);
});

process.on("SIGTERM", () => {
  log("SIGTERM received, unpublishing HomeKit bridge");
  accessory.unpublish();
  process.exit(0);
});
