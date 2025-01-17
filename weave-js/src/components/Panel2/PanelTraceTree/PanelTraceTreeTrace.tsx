import * as globals from '@wandb/weave/common/css/globals.styles';
import {SpanKindType, SpanType} from '@wandb/weave/core/model/media/traceTree';
import _ from 'lodash';
import React, {ReactNode, useMemo} from 'react';
import {Loader} from 'semantic-ui-react';
import styled from 'styled-components';

import {useUpdatingState} from '../../../hookUtils';
import {useNodeValue} from '../../../react';
import {AgentSVG, ChainSVG, LLMSVG, ToolSVG} from '../Icons';
import * as Panel2 from '../panel';
import {PanelFullscreenContext} from '../PanelComp';
import {TooltipTrigger} from '../Tooltip';
import {
  agentColor,
  agentTextColor,
  chainColor,
  chainTextColor,
  llmColor,
  llmTextColor,
  MinimalTooltip,
  toolColor,
  toolTextColor,
} from './common';
import * as S from './lct.style';
import {useTipOverlay} from './tipOverlay';
import {useTimelineZoomAndPan} from './zoomAndPan';

const inputType = {
  type: 'wb_trace_tree' as const,
};

type PanelTraceTreeTraceConfigType = {};

type PanelTraceTreeTraceProps = Panel2.PanelProps<
  typeof inputType,
  PanelTraceTreeTraceConfigType
>;

type SpanKindStyle = {
  color: string;
  textColor: string;
  label: string;
  icon: ReactNode;
};

function getSpanKindStyle(kind?: SpanKindType): SpanKindStyle {
  switch (kind) {
    case 'CHAIN':
      return {
        color: chainColor,
        textColor: chainTextColor,
        label: `Chain`,
        icon: <ChainSVG />,
      };
    case 'AGENT':
      return {
        color: agentColor,
        textColor: agentTextColor,
        label: `Agent`,
        icon: <AgentSVG />,
      };
    case 'TOOL':
      return {
        color: toolColor,
        textColor: toolTextColor,
        label: `Tool`,
        icon: <ToolSVG />,
      };
    case 'LLM':
      return {
        color: llmColor,
        textColor: llmTextColor,
        label: `LLM`,
        icon: <LLMSVG />,
      };
    default:
      return {
        color: '#f3f3f3',
        textColor: '#494848',
        label: `Span`,
        icon: <></>,
      };
  }
}

const PanelTraceTreeTrace: React.FC<PanelTraceTreeTraceProps> = props => {
  const nodeValue = useNodeValue(props.input);
  const [traceSpan, setTraceSpan] = React.useState<null | SpanType>(null);
  React.useEffect(() => {
    if (nodeValue.result) {
      try {
        const rootSpan = JSON.parse(
          nodeValue.result.root_span_dumps
        ) as SpanType;
        setTraceSpan(rootSpan);
      } catch (e) {
        console.log(e);
      }
    }
  }, [nodeValue.result]);

  if (nodeValue.loading) {
    return <Loader />;
  }

  if (traceSpan == null) {
    return <div></div>;
  }

  return <TraceTreeSpanViewer span={traceSpan} />;
};

const TraceTreeSpanViewer: React.FC<{
  span: SpanType;
}> = props => {
  const {isFullscreen} = React.useContext(PanelFullscreenContext);
  const split = isFullscreen ? `horizontal` : `vertical`;

  const span = props.span;
  const [selectedSpan, setSelectedSpan] = useUpdatingState<SpanType>(span);

  const {tipOverlay, showTipOverlay} = useTipOverlay();

  const {timelineRef, timelineStyle, scale} = useTimelineZoomAndPan({
    onHittingMinZoom: showTipOverlay,
  });

  return (
    <S.TraceWrapper split={split}>
      <S.TraceTimelineWrapper split={split}>
        <S.TraceTimeline
          ref={timelineRef}
          style={timelineStyle}
          onClick={e => {
            e.stopPropagation();
          }}>
          <SpanElement
            span={span}
            setSelectedTrace={setSelectedSpan}
            selectedTrace={selectedSpan}
            scale={scale}
          />
        </S.TraceTimeline>
        {tipOverlay}
      </S.TraceTimelineWrapper>
      {selectedSpan && (
        <S.TraceDetail split={split}>
          <SpanTreeDetail span={selectedSpan} />
        </S.TraceDetail>
      )}
    </S.TraceWrapper>
  );
};

const getSpanIdentifier = (span: SpanType) => {
  return span.name ?? span.span_kind ?? 'Unknown';
};

const getSpanDuration = (span: SpanType) => {
  if (span.end_time_ms && span.start_time_ms) {
    return span.end_time_ms - span.start_time_ms;
  }
  return null;
};

const TooltipTriggerWrapper = styled.div`
  position: relative;

  &&&.tooltip-open:before {
    content: '';
    position: absolute;
    top: 0;
    bottom: 0;
    left: 0;
    right: 0;
    background-color: ${globals.hexToRGB(globals.BLACK, 0.04)};
    pointer-events: none;
  }
`;

const TooltipFrame = styled.div`
  padding: 4px 8px;
  background-color: ${globals.WHITE};
  border: 1px solid ${globals.GRAY_200};
`;

const TooltipBody = styled.div`
  font-family: 'Inconsolata';
  font-size: 12px;
  line-height: 140%;
  white-space: nowrap;
`;

const TooltipLine = styled.div<{bold?: boolean; red?: boolean}>`
  ${p => p.bold && `font-weight: 600;`}
  ${p => p.red && `color: ${globals.RED_DARK};`}
`;

const SpanElement: React.FC<{
  span: SpanType;
  selectedTrace: SpanType | null;
  setSelectedTrace: (trace: SpanType) => void;
  scale?: number;
}> = ({span, selectedTrace, setSelectedTrace, scale}) => {
  const identifier = getSpanIdentifier(span);
  const trueDuration = getSpanDuration(span);
  let effectiveDuration = Math.max(1, span.child_spans?.length ?? 0);
  if (trueDuration) {
    effectiveDuration = Math.max(trueDuration, effectiveDuration);
  }

  const hasError = span.status_code === 'ERROR';
  const isSelected = selectedTrace === span;
  const kindStyle = getSpanKindStyle(span.span_kind);
  const executionOrder = span.attributes?.execution_order ?? null;
  const orderedChildSpans = useMemo(
    () =>
      _.sortBy(span.child_spans ?? [], s => {
        return s.start_time_ms ?? 0;
      }),
    [span.child_spans]
  );

  const tooltipContent = useMemo(() => {
    return (
      <>
        <TooltipLine bold>{identifier}</TooltipLine>
        <TooltipLine>{kindStyle.label}</TooltipLine>
        {hasError && <TooltipLine red>Error</TooltipLine>}
        {trueDuration != null && (
          <TooltipLine red={hasError}>{trueDuration}ms</TooltipLine>
        )}
      </>
    );
  }, [identifier, kindStyle.label, hasError, trueDuration]);

  return (
    <S.TraceTimelineElementWrapper
      style={scale != null ? {width: `${100 * scale}%`} : undefined}>
      <TooltipTrigger
        content={tooltipContent}
        showWithoutOverflow
        showInFullscreen
        noHeader
        padding={0}
        positionNearMouse
        TriggerWrapperComp={TooltipTriggerWrapper}
        FrameComp={TooltipFrame}
        BodyComp={TooltipBody}>
        <S.SpanElementHeader
          hasError={hasError}
          isSelected={isSelected}
          backgroundColor={kindStyle.color}
          color={kindStyle.textColor}
          onClick={e => {
            e.stopPropagation();
            setSelectedTrace(span);
          }}>
          <span>
            {executionOrder != null ? `${executionOrder}: ` : ''}
            {kindStyle.icon}
            {identifier}
          </span>
          {trueDuration != null && (
            <S.DurationLabel>{trueDuration}ms</S.DurationLabel>
          )}
        </S.SpanElementHeader>
      </TooltipTrigger>
      {orderedChildSpans != null && orderedChildSpans.length > 0 && (
        <S.SpanElementChildSpansWrapper>
          {orderedChildSpans.map((child, i) => {
            let effectiveChildDuration: number = 1;
            const childDuration = getSpanDuration(child);
            if (childDuration) {
              effectiveChildDuration = Math.max(
                effectiveChildDuration,
                childDuration
              );
            }
            const dur = effectiveChildDuration / effectiveDuration;
            const parentStartTime = Math.min(
              span.start_time_ms ?? 0,
              child.start_time_ms ?? 0
            );
            const childStartTime = Math.max(
              parentStartTime,
              child.start_time_ms ?? i
            );
            const offset =
              (childStartTime - parentStartTime) / effectiveDuration;
            return (
              <SpanElementChildRun key={i} offsetPct={offset} durationPct={dur}>
                <SpanElement
                  span={child}
                  setSelectedTrace={setSelectedTrace}
                  selectedTrace={selectedTrace}
                />
              </SpanElementChildRun>
            );
          })}
        </S.SpanElementChildSpansWrapper>
      )}
    </S.TraceTimelineElementWrapper>
  );
};

const SpanElementChildRun: React.FC<{
  offsetPct: number;
  durationPct: number;
  children: React.ReactNode;
}> = props => {
  return (
    <S.SpanElementChildSpanWrapper>
      <div
        style={{
          width: `${props.offsetPct * 100}%`,
          flexBasis: `${props.offsetPct * 100}%`,
        }}>
        {' '}
      </div>
      <div
        style={{
          width: `${props.durationPct * 100}%`,
          flexBasis: `${props.durationPct * 100}%`,
        }}>
        {props.children}
      </div>
    </S.SpanElementChildSpanWrapper>
  );
};

const SpanTreeDetail: React.FC<{
  span: SpanType;
}> = props => {
  const {span} = props;
  const kindStyle = getSpanKindStyle(span.span_kind);
  const identifier = getSpanIdentifier(span);
  const duration = getSpanDuration(span);

  return (
    <S.TraceDetailWrapper>
      <S.SpanDetailWrapper>
        <S.SpanDetailHeader>
          <span>
            <span
              style={{
                color: kindStyle.textColor,
              }}>
              {kindStyle.icon}
            </span>
            {identifier}
          </span>
          {duration != null && <S.DurationLabel>{duration}ms</S.DurationLabel>}
        </S.SpanDetailHeader>
        <S.SpanDetailTable>
          <tbody>
            {span.status_message != null && (
              <DetailKeyValueRow
                style={{
                  color: span.status_code === 'ERROR' ? '#EB1C45' : undefined,
                }}
                label="Status Message"
                value={span.status_message}
              />
            )}
            {span.results != null && (
              <>
                {span.results.map((result, i) => {
                  return (
                    <React.Fragment key={i}>
                      <tr>
                        <S.SpanDetailSectionHeaderTd colSpan={2}>
                          Result Set {i + 1}
                        </S.SpanDetailSectionHeaderTd>
                      </tr>
                      {result.inputs != null && (
                        <React.Fragment>
                          <tr>
                            <S.SpanDetailIOSectionHeaderTd colSpan={2}>
                              Inputs
                            </S.SpanDetailIOSectionHeaderTd>
                          </tr>
                          {Object.entries(result.inputs).map(
                            ([key, value], j) => {
                              return (
                                <DetailKeyValueRow
                                  key={j}
                                  label={key}
                                  value={value}
                                />
                              );
                            }
                          )}
                        </React.Fragment>
                      )}
                      {result.outputs != null && (
                        <React.Fragment>
                          <tr>
                            <S.SpanDetailIOSectionHeaderTd colSpan={2}>
                              Outputs
                            </S.SpanDetailIOSectionHeaderTd>
                          </tr>
                          {Object.entries(result.outputs).map(
                            ([key, value], j) => {
                              return (
                                <DetailKeyValueRow
                                  key={j}
                                  label={key}
                                  value={value}
                                />
                              );
                            }
                          )}
                        </React.Fragment>
                      )}
                    </React.Fragment>
                  );
                })}
              </>
            )}
            <tr>
              <S.SpanDetailSectionHeaderTd colSpan={2}>
                Metadata
              </S.SpanDetailSectionHeaderTd>
            </tr>
            {span.span_id != null && (
              <DetailKeyValueRow label="ID" value={span.span_id} />
            )}
            {span.span_kind != null && (
              <DetailKeyValueRow label="Kind" value={span.span_kind} />
            )}
            {span.status_code != null && (
              <DetailKeyValueRow label="Status" value={span.status_code} />
            )}
            {span.start_time_ms != null && (
              <DetailKeyValueRow
                label="Start Time"
                value={'' + new Date(span.start_time_ms)}
              />
            )}
            {span.end_time_ms != null && (
              <DetailKeyValueRow
                label="End Time"
                value={'' + new Date(span.end_time_ms)}
              />
            )}
            {span.child_spans != null && span.child_spans.length > 0 && (
              <DetailKeyValueRow
                label="Child Spans"
                value={span.child_spans.length}
              />
            )}
            {span.attributes != null &&
              Object.entries(span.attributes).map(([key, value], i) => {
                return <DetailKeyValueRow key={i} label={key} value={value} />;
              })}
          </tbody>
        </S.SpanDetailTable>
      </S.SpanDetailWrapper>
    </S.TraceDetailWrapper>
  );
};

const safeValue = (value: any) => {
  return typeof value === 'string' ? value : JSON.stringify(value, null, 2);
};

const DetailKeyValueRow: React.FC<{
  label: string;
  value: any;
  style?: React.CSSProperties;
}> = props => {
  const {label, value} = props;
  const textValue = safeValue(value);
  return (
    <tr style={props.style}>
      <S.KVDetailKeyTD>{'' + label}</S.KVDetailKeyTD>
      <S.KVDetailValueTD>
        <MinimalTooltip text={textValue}>
          <S.KVDetailValueText>{textValue}</S.KVDetailValueText>
        </MinimalTooltip>
      </S.KVDetailValueTD>
    </tr>
  );
};

export const Spec: Panel2.PanelSpec = {
  id: 'wb_trace_tree-traceViewer',
  canFullscreen: true,
  Component: PanelTraceTreeTrace,
  inputType,
};
